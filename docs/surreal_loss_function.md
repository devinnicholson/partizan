# Game-Theoretic Representation Learning: The Surreal Loss Function

Standard Deep Reinforcement Learning for perfect-information games (like AlphaZero) uses a scalar output head to predict the expected value of a state $v \in [-1, 1]$. The loss is calculated using Mean Squared Error (MSE) against the actual game outcome ($z$).

This approach reduces complex combinatorial game states to mere probability scalars, completely losing the structural information of the game tree (such as mutual zugzwang, forcing combinations, or independent local battles). 

To train an AI on the **Partizan** tablebase, we introduce the **Surreal Loss Function ($L_{surreal}$)**.

## 1. The Output Representation
In Combinatorial Game Theory (CGT), every game $G$ can be summarized by two critical thermodynamic properties:
1. **Mean Value $m(G)$**: The average advantage (positive for Left/White, negative for Right/Black).
2. **Temperature $t(G)$**: The urgency of making a move. A high temperature means moving is highly advantageous (a chaotic, tactical position). A zero or negative temperature means neither player wants to move (zugzwang or a dead position).

Instead of predicting a single scalar $v$, our Neural Network will output a **Surreal Vector**: $\hat{y} = [\hat{m}, \hat{t}]$.

## 2. The Surreal Loss Formulation
Given a ground-truth Combinatorial Tablebase that provides the exact canonical game tree for a position, we compute the true mean $m$ and true temperature $t$.

The loss function is a weighted sum of the Mean error and the Temperature error:

$$ L_{surreal}(\theta) = \alpha (\hat{m} - m)^2 + \beta (\hat{t} - t)^2 $$

### Why this is a breakthrough:
By forcing the network to predict the *temperature* ($t$), the AI learns to encode the **tactical volatility** of the board. If a sub-game has a temperature of $3.0$, the network mathematically understands that a piece sacrifice here is justified if it forces a response, because it cools the game tree. 

Standard engines only learn this implicitly through millions of playouts. Our network learns it explicitly through $L_{surreal}$.

## 3. Dealing with Infinitesimals and Nimbers
Certain endgames evaluate to infinitesimals (e.g., $\uparrow, \downarrow, \ast$). 
To handle these, the output head can be expanded to a probability distribution over discrete CGT classes (e.g., a Softmax head over $\{0, \ast, \uparrow, \downarrow\}$) for positions where $t(G) \approx 0$.

$$ L_{class} = -\sum_{c \in C} y_c \log(\hat{y}_c) $$

The final loss function becomes:
$$ L_{total} = L_{policy} + L_{surreal} + L_{class} $$
