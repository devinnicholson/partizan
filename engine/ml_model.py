import torch
import torch.nn as nn
import torch.nn.functional as F

class ResidualBlock(nn.Module):
    def __init__(self, channels):
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(channels)
        self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(channels)

    def forward(self, x):
        residual = x
        x = F.relu(self.bn1(self.conv1(x)))
        x = self.bn2(self.conv2(x))
        x += residual
        return F.relu(x)

class PartizanNet(nn.Module):
    """
    A Neural Network designed to predict Combinatorial Game Theory (CGT) values.
    Instead of outputting a scalar Win/Loss probability, it outputs a Surreal Vector.
    """
    def __init__(self, num_blocks=10, channels=128):
        super().__init__()
        # Input layer (e.g., 14 channels for pieces/colors/castling over 8x8)
        self.conv_input = nn.Conv2d(14, channels, kernel_size=3, padding=1)
        self.bn_input = nn.BatchNorm2d(channels)
        
        # Residual tower
        self.res_blocks = nn.ModuleList([ResidualBlock(channels) for _ in range(num_blocks)])
        
        # Policy Head (Standard: predicts the best move)
        self.policy_conv = nn.Conv2d(channels, 2, kernel_size=1)
        self.policy_bn = nn.BatchNorm2d(2)
        self.policy_fc = nn.Linear(2 * 8 * 8, 4096) # Simplified move vector
        
        # The Surreal Head (Novelty: predicts CGT Mean and Temperature)
        self.surreal_conv = nn.Conv2d(channels, 1, kernel_size=1)
        self.surreal_bn = nn.BatchNorm2d(1)
        self.surreal_fc1 = nn.Linear(64, 64)
        self.surreal_fc2 = nn.Linear(64, 2) # Outputs [Mean, Temperature]
        
        # The Infinitesimal Head (Predicts probabilities of *, ^, v, 0)
        self.infinitesimal_fc = nn.Linear(64, 4)

    def forward(self, x):
        x = F.relu(self.bn_input(self.conv_input(x)))
        for block in self.res_blocks:
            x = block(x)
            
        # Policy
        p = F.relu(self.policy_bn(self.policy_conv(x)))
        p = p.view(p.size(0), -1)
        policy_logits = self.policy_fc(p)
        
        # Surreal
        s = F.relu(self.surreal_bn(self.surreal_conv(x)))
        s = s.view(s.size(0), -1)
        s_hidden = F.relu(self.surreal_fc1(s))
        
        surreal_vector = self.surreal_fc2(s_hidden) # [m(G), t(G)]
        infinitesimal_logits = self.infinitesimal_fc(s_hidden)
        
        return policy_logits, surreal_vector, infinitesimal_logits

def surreal_loss(pred_vector, target_vector, alpha=1.0, beta=1.0):
    """
    The Surreal Loss Function:
    Penalizes network for incorrect Mean value and incorrect Temperature.
    """
    pred_mean, pred_temp = pred_vector[:, 0], pred_vector[:, 1]
    target_mean, target_temp = target_vector[:, 0], target_vector[:, 1]
    
    mean_loss = F.mse_loss(pred_mean, target_mean)
    temp_loss = F.mse_loss(pred_temp, target_temp)
    
    return alpha * mean_loss + beta * temp_loss
