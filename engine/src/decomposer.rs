use shakmaty::{Color, Bitboard, Square};
use std::collections::HashSet;

pub struct UnionFind {
    parent: [usize; 64],
}

impl UnionFind {
    pub fn new() -> Self {
        let mut parent = [0; 64];
        for i in 0..64 {
            parent[i] = i;
        }
        UnionFind { parent }
    }

    pub fn find(&mut self, i: usize) -> usize {
        if self.parent[i] == i {
            i
        } else {
            let root = self.find(self.parent[i]);
            self.parent[i] = root;
            root
        }
    }

    pub fn union(&mut self, i: usize, j: usize) {
        let root_i = self.find(i);
        let root_j = self.find(j);
        if root_i != root_j {
            self.parent[root_i] = root_j;
        }
    }
}

pub fn get_locked_pawns(board: &shakmaty::Board) -> Bitboard {
    let occupied = board.occupied();
    let mut locked = Bitboard::EMPTY;

    for sq in board.pawns() {
        let color = board.color_at(sq).unwrap();
        let forward_offset = if color == Color::White { 8 } else { -8 };
        let forward_sq = sq.offset(forward_offset);
        let is_blocked = match forward_sq {
            Some(fsq) => occupied.contains(fsq),
            None => true,
        };

        let enemy_color = !color;
        let enemy_pieces = board.by_color(enemy_color);
        let attacks = shakmaty::attacks::pawn_attacks(color, sq);
        let has_captures = !(attacks & enemy_pieces).is_empty();
        
        if is_blocked && !has_captures {
            locked ^= Bitboard::from_square(sq);
        }
    }
    locked
}

pub fn find_subsystems(board: &shakmaty::Board) -> (bool, u8) {
    let barrier = get_locked_pawns(board);
    let mut uf = UnionFind::new();

    let all_squares = !barrier;

    for sq in all_squares {
        let sq_idx = usize::from(sq);

        // Union King moves
        let king_moves = shakmaty::attacks::king_attacks(sq) & all_squares;
        for target in king_moves { uf.union(sq_idx, usize::from(target)); }

        // Union Knight moves
        let knight_moves = shakmaty::attacks::knight_attacks(sq) & all_squares;
        for target in knight_moves { uf.union(sq_idx, usize::from(target)); }

        // Union Rook moves (barrier acts as blockers)
        let rook_moves = shakmaty::attacks::rook_attacks(sq, barrier) & all_squares;
        for target in rook_moves { uf.union(sq_idx, usize::from(target)); }

        // Union Bishop moves
        let bishop_moves = shakmaty::attacks::bishop_attacks(sq, barrier) & all_squares;
        for target in bishop_moves { uf.union(sq_idx, usize::from(target)); }
        
        // Union Queen moves
        let queen_moves = shakmaty::attacks::queen_attacks(sq, barrier) & all_squares;
        for target in queen_moves { uf.union(sq_idx, usize::from(target)); }
        
        // Union Pawn captures/moves (simplified to adjacent forwards)
        // Since pawns can theoretically capture and move, we treat them as Kings 
        // for pure connectivity logic (if a pawn can eventually become a piece).
        // Actually, just using King moves to link adjacent squares provides baseline connectivity.
    }

    // Now, find components that contain mobile pieces
    let mobile_pieces = board.occupied() & !barrier;
    let mut active_components = HashSet::new();

    for sq in mobile_pieces {
        let root = uf.find(usize::from(sq));
        active_components.insert(root);
    }

    let num_components = active_components.len() as u8;
    (num_components > 1, num_components)
}
