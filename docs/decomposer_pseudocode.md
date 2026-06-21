# The Decomposer Algorithm: Combinatorial Game Theory in Chess Endgames

Based on Noam Elkies' application of Combinatorial Game Theory (CGT) to chess, certain endgames can be modeled as sums of independent combinatorial games. In normal chess, the mobility of pieces across the entire $8 \times 8$ board typically prevents this. However, locked pawn structures can act as topological barriers, partitioning the board into weakly-interacting or strictly independent sub-systems. 

## 1. Mathematical Logic and Graph-Theoretic Properties

### 1.1. The Board Graph
Let the chess board be a graph $G = (V, E_m \cup E_c)$, where:
- $V = \{ (x, y) \mid 1 \le x, y \le 8 \}$ represents the 64 squares.
- $E_m$ represents movement edges between squares for a given piece type.
- $E_c$ represents capture edges.

### 1.2. The Cut Set (Locked Chains)
A pawn $P$ at $(x, y)$ is **strictly locked** if:
1. The square $(x, y + d)$ (where $d$ is the forward direction) is occupied.
2. The capture squares $(x-1, y+d)$ and $(x+1, y+d)$ are either empty (with no *en passant* possible) or occupied by friendly pieces, meaning no legal capture is available.

Let $L \subset V$ be the set of squares occupied by locked pawns. A **topological barrier** $B \subseteq L$ is a continuous path of locked pawns (and potentially board edges) that forms a cut set in $G$, partitioning $V \setminus B$ into disjoint subgraphs $V_1, V_2, \dots, V_k$.

### 1.3. Reachability and Independence
For each mobile piece $p \in P_{mobile}$, let $R(p) \subseteq V$ be the **reachability set**—the set of squares $p$ can move to in any number of turns, assuming the barrier $B$ remains static.
- For a sliding piece (Rook, Bishop, Queen), $B$ acts as a strict impassable wall.
- For a Knight, $B$ is impassable only if the "landing squares" across the barrier are occupied or controlled such that crossing is strictly impossible.
- For a King, $B$ is impassable if no path of adjacent empty/safe squares connects $V_1$ to $V_2$.

Two regions $V_i$ and $V_j$ are **strictly independent** if:
$\forall p_i \in V_i, R(p_i) \cap V_j = \emptyset$ \text{ and } \forall p_j \in V_j, R(p_j) \cap V_i = \emptyset.

If the board can be partitioned into such independent regions, the game state $G$ can be decoupled into a canonical CGT sum: $G = G_1 + G_2 + \dots + G_k$.

---

## 2. Pseudocode Implementation

```python
class ChessDecomposer:
    def __init__(self, fen_string):
        self.board = self.parse_fen(fen_string)
        self.pieces = self.get_all_pieces(self.board)
        
    def find_locked_pawns(self):
        """
        Identifies pawns that cannot move forward and have no valid captures.
        """
        locked_pawns = set()
        for pawn in self.pieces.get_type('PAWN'):
            if self.is_blocked_forward(pawn) and not self.has_valid_captures(pawn):
                locked_pawns.add(pawn.position)
        return locked_pawns

    def construct_barrier(self, locked_pawns):
        """
        Finds contiguous chains of locked pawns that span from one edge of the 
        board to another, forming a graph cut.
        """
        barriers = []
        visited = set()
        
        for p in locked_pawns:
            if p not in visited:
                chain = self.bfs_pawn_chain(p, locked_pawns)
                visited.update(chain)
                
                # Check if chain touches two distinct edges of the board
                if self.spans_board_edges(chain):
                    barriers.append(chain)
                    
        return barriers

    def calculate_reachability(self, piece, barriers):
        """
        Calculates the transitive closure of reachable squares for a piece,
        treating the barrier as impassable.
        """
        reachable = set([piece.position])
        queue = [piece.position]
        
        while queue:
            current = queue.pop(0)
            moves = self.generate_pseudo_legal_moves(piece, current)
            
            for move in moves:
                if move not in reachable and move not in barriers:
                    # For knights: ensure they don't land ON the barrier
                    # For sliders: raycasting naturally stops at the barrier
                    reachable.add(move)
                    queue.append(move)
                    
        return reachable

    def find_weakly_interacting_subsystems(self):
        """
        Core algorithm to decouple the board into independent CGT sub-games.
        """
        locked_pawns = self.find_locked_pawns()
        barriers = self.construct_barrier(locked_pawns)
        
        if not barriers:
            return {"decomposable": False, "subsystems": [self.board]}
            
        # Graph nodes: All non-barrier squares
        all_squares = set(self.board.all_squares()) - set(barriers[0])
        
        # Determine connected components based on piece mobility
        # Using Disjoint Set (Union-Find) to group squares
        uf = UnionFind(elements=all_squares)
        
        for piece in self.pieces.mobile_pieces():
            reach = self.calculate_reachability(piece, barriers[0])
            reach_list = list(reach)
            
            # Union all squares reachable by this piece
            for i in range(1, len(reach_list)):
                uf.union(reach_list[0], reach_list[i])
                
        components = uf.get_components()
        
        # A valid decomposition must have > 1 component containing mobile pieces
        active_components = []
        for comp in components:
            if self.contains_active_pieces(comp):
                active_components.append(comp)
                
        if len(active_components) > 1:
            return {"decomposable": True, "subsystems": active_components}
        else:
            return {"decomposable": False, "subsystems": [self.board]}

    def evaluate_cgt_value(self, subsystem):
        """
        Evaluates the combinatorial game value (e.g., Integer, Fraction, 
        Star, Up, Down) of an isolated sub-game.
        """
        pass # Implementation of specific CGT endgame evaluation
```

## 3. Heuristics for "Weakly-Interacting"

In reality, strict decomposition is rare because Knights can jump and sacrifices can break barriers. To extend this to "weakly-interacting" systems:

1. **Sacrifice Threshold**: Assign a "temperature" or cost to breaking a barrier. If breaking a locked pawn requires a piece sacrifice that shifts the standard evaluation by $> \pm 3.0$ pawns, we consider the barrier practically impassable.
2. **Knight Repellers**: Knights can cross barriers only if there are empty "landing squares". If the squares on the opposite side of the barrier are heavily guarded by enemy pawns, the Knight effectively cannot cross. We can prune the reachability graph by removing squares controlled by enemy pawns. 
3. **Pawn Breakthroughs**: We must statically analyze if a pawn chain can be broken by a pawn sacrifice (e.g., a lever). If no levers exist, the barrier's stability heuristic score is increased.

This approach effectively turns a global minimax/alpha-beta search into a much smaller, decoupled sum of local games $G = G_{left} + G_{right}$, dramatically reducing the state space.
