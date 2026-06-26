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

import json
from torch.utils.data import Dataset, DataLoader
import torch.optim as optim

def fen_to_tensor(fen: str) -> torch.Tensor:
    """
    Converts a FEN string into a 14x8x8 tensor representation.
    (Simplified: 12 channels for pieces, 2 for auxiliary context).
    """
    pieces = {'P': 0, 'N': 1, 'B': 2, 'R': 3, 'Q': 4, 'K': 5,
              'p': 6, 'n': 7, 'b': 8, 'r': 9, 'q': 10, 'k': 11}
    
    tensor = torch.zeros(14, 8, 8)
    board_part = fen.split()[0]
    
    row, col = 0, 0
    for char in board_part:
        if char == '/':
            row += 1
            col = 0
        elif char.isdigit():
            col += int(char)
        elif char in pieces:
            channel = pieces[char]
            tensor[channel, row, col] = 1.0
            col += 1
            
    # Add some auxiliary features in the 12th/13th channels (e.g. turn flag)
    if len(fen.split()) > 1:
        turn = fen.split()[1]
        tensor[12, :, :] = 1.0 if turn == 'w' else 0.0
    tensor[13, :, :] = 1.0 # Board mask presence
    
    return tensor

class CGTDataset(Dataset):
    def __init__(self, jsonl_path):
        self.data = []
        with open(jsonl_path, 'r') as f:
            for line in f:
                if not line.strip(): continue
                self.data.append(json.loads(line))
                
    def __len__(self):
        return len(self.data)
        
    def __getitem__(self, idx):
        item = self.data[idx]
        fen = item['fen']
        
        # Target vector: [Mean, Temperature]
        target = torch.tensor([
            float(item['mean_value']), 
            float(item['temperature'])
        ], dtype=torch.float32)
        
        return fen_to_tensor(fen), target

def train_partizan_net(dataset_path="cgt_dataset.jsonl", epochs=5, batch_size=128, lr=0.001):
    print(f"🚀 Initializing PartizanNet Training Loop on {dataset_path}...")
    
    # 1. Load Data
    dataset = CGTDataset(dataset_path)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    print(f"📦 Loaded {len(dataset)} combinatorial game states.")
    
    # 2. Initialize Model & Optimizer
    # Dynamically detect hardware acceleration (MPS for Apple Silicon, CUDA for NVIDIA)
    device = torch.device("mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu"))
    print(f"⚡ Utilizing compute device: {device}")
    
    model = PartizanNet().to(device)
    optimizer = optim.Adam(model.parameters(), lr=lr)
    
    # 3. Training Loop
    model.train()
    for epoch in range(epochs):
        total_loss = 0.0
        for batch_idx, (features, targets) in enumerate(dataloader):
            features, targets = features.to(device), targets.to(device)
            
            # Forward Pass
            optimizer.zero_grad()
            _, surreal_pred, _ = model(features)
            
            # Compute Surreal Loss (optimizing Mean & Temperature accuracy)
            loss = surreal_loss(surreal_pred, targets, alpha=1.0, beta=2.0) # Weight temperature higher
            
            # Backward Pass
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            
        avg_loss = total_loss / len(dataloader)
        print(f"Epoch [{epoch+1}/{epochs}] - Surreal Loss: {avg_loss:.4f}")
        
    print("✅ Training Complete! PartizanNet has acquired early CGT valuation parameters.")
    return model

if __name__ == "__main__":
    import os
    if os.path.exists("cgt_dataset.jsonl"):
        train_partizan_net()
    else:
        print("Waiting for cgt_dataset.jsonl from Modal orchestrator...")
