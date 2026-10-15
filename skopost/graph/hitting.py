"""最小ヒッティングセット（関所）の厳密解・近似・代替案の列挙（担当 D・graph）。

問題：道具（頂点）の集合 V と、道ごとの道具の集合 P_i ⊆ V（|P_i| は 1 か 2）。すべての P_i と交わる
S ⊆ V のうち、(|S|, Σ frequency(S)) を辞書式に最小にするものを求める。同点は v1 と同じ鍵
（S の道具 id を allow の並び順に並べた列の辞書順）で決める。

手順（docs/GRAPH.md §2）：
1. |P_i| = 1 の道具は**強制**（必ず関所）。それで断てる道を外す。残りは 2 個組だけ＝グラフの辺。
2. 残りの辺が無ければ自明（method "trivial"）。
3. 残りのグラフが**二部**なら最大流で重み付き最小頂点被覆（König–Egerváry。method "bipartite-konig"）。
   SPEC §7 の道の全部を渡したときは、R と S の両方に入る道具が強制されるので**残りは常に完全二部**になる
   （読む側 × 送る側）。一般の道の部分集合（将来の 3 段・絞り込み）では二部にならないことがある。
4. 二部でなければ分枝限定（method "branch-and-bound"）。下界は極大マッチング。
5. 同じ大きさの被覆を列挙（手間の上位 max_alternatives+1 件より重い枝は切る・節数と時間の打ち切りあり）して
   frequency 合計と v1 の鍵で並べ、第一案と代替案にする。
   列挙を打ち切ったときは、第一案は「制約付きの再解」で鍵の最小を厳密に求める（最小手間を逃さない）。
6. 道具が exact_limit を超え、かつ時間切れ（time_budget_s）なら、貪欲法（v1 と同じ）＋下界を返し exact=False。
   貪欲の大きさが下界と一致すれば大きさは最小と証明できる（exact=True）が、そのときの frequency 合計の最小性は
   保証しない（docs に明記）。

重み：w(v) = BIG + frequency(v)、BIG = Σ frequency + 1。これで (大きさ, 手間) の辞書式最小＝重みの最小になる。
標準ライブラリのみ。頂点は 64 個以下を想定（ビット集合）。
"""
from __future__ import annotations

import heapq
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

from ..model.types import Checkpoints

#: 代替案の列挙で訪れる探索節の上限（これを超えたら打ち切り、第一案は制約付き再解で求める）
ENUM_NODE_CAP = 200_000
#: 列挙で保持する被覆の上限
ENUM_COVER_CAP = 20_000


class Timeout(Exception):
    pass


class Infeasible(Exception):
    pass


@dataclass(frozen=True)
class Instance:
    ids: tuple[str, ...]          # allow の道具 id（並び順＝添字）
    freq: tuple[int, ...]
    sets: tuple[frozenset, ...]   # 添字の集合（大きさ 1 か 2）。重複は除いてある

    @property
    def n(self) -> int:
        return len(self.ids)


def make_instance(ids: Sequence[str], freq: Sequence[int], tool_sets: Sequence[frozenset]) -> Instance:
    idx = {tid: i for i, tid in enumerate(ids)}
    if len(idx) != len(ids):
        raise ValueError("id が重複")
    out: set[frozenset] = set()
    for s in tool_sets:
        if not s:
            raise ValueError("空の道")
        if len(s) > 2:
            raise ValueError(f"3 個以上の道具を含む道は未対応（{sorted(s)}）")
        missing = [t for t in s if t not in idx]
        if missing:
            raise ValueError(f"allow でない・存在しない道具が道に含まれる：{missing}")
        out.add(frozenset(idx[t] for t in s))
    return Instance(tuple(ids), tuple(int(f) for f in freq), tuple(sorted(out, key=lambda s: sorted(s))))


# ---------------------------------------------------------------- 準備
def _popcount(x: int) -> int:
    return bin(x).count("1")


def _bits(x: int):
    while x:
        b = x & -x
        yield b.bit_length() - 1
        x ^= b


@dataclass
class _Residual:
    """強制と制約を畳んだ後の残りのグラフ。"""
    forced: int          # 必ず入れる頂点（ビット集合）
    alive: int           # まだ決めていない頂点（辺を持つものだけ）
    adj: list[int]       # 頂点ごとの隣接（alive の中だけ有効）


def _reduce(inst: Instance, forced_in: int = 0, forced_out: int = 0) -> _Residual:
    """単独の道の強制・制約（forced_in／forced_out）を畳む。矛盾は Infeasible。"""
    n = inst.n
    adj = [0] * n
    forced = forced_in
    for s in inst.sets:
        if len(s) == 1:
            (v,) = s
            forced |= 1 << v
        else:
            u, v = s
            adj[u] |= 1 << v
            adj[v] |= 1 << u
    if forced & forced_out:
        raise Infeasible
    # forced_out の頂点の辺は相手が持つ。相手も forced_out なら矛盾
    for v in _bits(forced_out):
        nb = adj[v]
        if nb & forced_out:
            raise Infeasible
        forced |= nb
    if forced & forced_out:
        raise Infeasible
    alive = 0
    for v in range(n):
        if (forced | forced_out) >> v & 1:
            continue
        if adj[v] & ~(forced | forced_out):
            alive |= 1 << v
    return _Residual(forced, alive, adj)


def _is_bipartite(alive: int, adj: list[int]) -> Optional[tuple[int, int]]:
    """二部なら (左の集合, 右の集合)、そうでなければ None。"""
    color: dict[int, int] = {}
    left = right = 0
    for s in _bits(alive):
        if s in color:
            continue
        color[s] = 0
        q = deque([s])
        while q:
            u = q.popleft()
            for v in _bits(adj[u] & alive):
                if v not in color:
                    color[v] = color[u] ^ 1
                    q.append(v)
                elif color[v] == color[u]:
                    return None
    for v, c in color.items():
        if c == 0:
            left |= 1 << v
        else:
            right |= 1 << v
    return left, right


def _matching_lb(alive: int, adj: list[int], w: Sequence[int]) -> int:
    """極大マッチングによる下界（辺ごとに軽い方の重み）。"""
    used = 0
    lb = 0
    for u in _bits(alive):
        if used >> u & 1:
            continue
        cand = adj[u] & alive & ~used
        if cand:
            # 相手は重みが最小のもの（下界を大きくする）
            v = min(_bits(cand), key=lambda x: (w[x], x))
            used |= (1 << u) | (1 << v)
            lb += min(w[u], w[v])
    return lb


# ---------------------------------------------------------------- 二部：最大流
class _Dinic:
    def __init__(self, n: int) -> None:
        self.n = n
        self.g: list[list[list[int]]] = [[] for _ in range(n)]  # [to, cap, rev]

    def add(self, u: int, v: int, cap: int) -> None:
        self.g[u].append([v, cap, len(self.g[v])])
        self.g[v].append([u, 0, len(self.g[u]) - 1])

    def flow(self, s: int, t: int) -> int:
        total = 0
        while True:
            level = [-1] * self.n
            level[s] = 0
            q = deque([s])
            while q:
                u = q.popleft()
                for v, cap, _ in self.g[u]:
                    if cap > 0 and level[v] < 0:
                        level[v] = level[u] + 1
                        q.append(v)
            if level[t] < 0:
                return total
            it = [0] * self.n

            def dfs(u: int, f: int) -> int:
                if u == t:
                    return f
                while it[u] < len(self.g[u]):
                    e = self.g[u][it[u]]
                    v, cap, rev = e
                    if cap > 0 and level[v] == level[u] + 1:
                        d = dfs(v, min(f, cap))
                        if d > 0:
                            e[1] -= d
                            self.g[v][rev][1] += d
                            return d
                    it[u] += 1
                return 0

            while True:
                f = dfs(s, 1 << 62)
                if f == 0:
                    break
                total += f

    def reachable(self, s: int) -> set[int]:
        seen = {s}
        q = deque([s])
        while q:
            u = q.popleft()
            for v, cap, _ in self.g[u]:
                if cap > 0 and v not in seen:
                    seen.add(v)
                    q.append(v)
        return seen


def _bipartite_cover(res: _Residual, left: int, right: int, w: Sequence[int]) -> tuple[int, int]:
    """重み付き最小頂点被覆（二部）。返り値 (重み, 被覆のビット集合)。alive の辺だけを見る。"""
    n = len(w)
    S, T = n, n + 1
    D = _Dinic(n + 2)
    big = 1 << 60
    for u in _bits(left):
        D.add(S, u, w[u])
        for v in _bits(res.adj[u] & right):
            D.add(u, v, big)
    for v in _bits(right):
        D.add(v, T, w[v])
    cost = D.flow(S, T)
    reach = D.reachable(S)
    cover = 0
    for u in _bits(left):
        if u not in reach:
            cover |= 1 << u
    for v in _bits(right):
        if v in reach:
            cover |= 1 << v
    assert sum(w[v] for v in _bits(cover)) == cost
    return cost, cover


# ---------------------------------------------------------------- 一般：分枝限定
class _BB:
    def __init__(self, adj: list[int], w: Sequence[int], deadline: Optional[float]) -> None:
        self.adj = adj
        self.w = w
        self.deadline = deadline
        self.best_cost = 1 << 62
        self.best_cover = 0
        self.nodes = 0

    def _tick(self) -> None:
        self.nodes += 1
        if self.deadline is not None and (self.nodes & 255) == 0 and time.perf_counter() > self.deadline:
            raise Timeout

    def run(self, alive: int, cover: int, cost: int) -> None:
        self._tick()
        adj, w = self.adj, self.w
        # 次数 0 を落とす・次数 1 の規則（相手の方が軽ければ相手を取る）
        changed = True
        while changed:
            changed = False
            for v in _bits(alive):
                nb = adj[v] & alive
                if nb == 0:
                    alive &= ~(1 << v)
                    changed = True
                elif nb & (nb - 1) == 0:
                    u = nb.bit_length() - 1
                    if w[u] <= w[v]:
                        cover |= 1 << u
                        cost += w[u]
                        alive &= ~((1 << u) | (1 << v))
                        changed = True
                        break
        if cost >= self.best_cost:
            return
        if alive == 0:
            self.best_cost, self.best_cover = cost, cover
            return
        if cost + _matching_lb(alive, adj, w) >= self.best_cost:
            return
        # 分枝：次数最大の頂点（同点は添字が小さい方）
        v = max(_bits(alive), key=lambda x: (_popcount(adj[x] & alive), -x))
        nb = adj[v] & alive
        # 枝 1：v を入れる
        self.run(alive & ~(1 << v), cover | (1 << v), cost + w[v])
        # 枝 2：v を入れない → 隣を全部入れる
        add = sum(w[u] for u in _bits(nb))
        self.run(alive & ~(1 << v) & ~nb, cover | nb, cost + add)


# ---------------------------------------------------------------- 列挙（同じ大きさの被覆）
class _Enum:
    """大きさが k の被覆を列挙する。手間（frequency 合計）の小さい順に上位 keep 件だけが要るので、
    「keep 件目の手間」より確実に重くなる枝は切る（同じ手間は切らない＝同点の鍵の比較に要る）。
    最小の (手間, 鍵) の被覆は決して切られないので、列挙が完了すれば第一案と代替案は厳密。"""

    def __init__(self, adj: list[int], freq: Sequence[int], k: int, keep: int, deadline: Optional[float]) -> None:
        self.adj = adj
        self.freq = freq
        self.k = k
        self.keep = max(1, keep)
        self.deadline = deadline
        self.found: list[int] = []
        self._heap: list[int] = []   # 見つけた被覆の手間（負にした最大ヒープ・keep 件まで）
        self.bound = 1 << 62         # keep 件目の手間（これより重い被覆は要らない）
        self.nodes = 0
        self.complete = True
        self._ones = [1] * len(freq)

    def _record(self, cover: int) -> None:
        f = sum(self.freq[i] for i in _bits(cover))
        if f > self.bound:
            return
        self.found.append(cover)
        heapq.heappush(self._heap, -f)
        if len(self._heap) > self.keep:
            heapq.heappop(self._heap)
        if len(self._heap) == self.keep:
            self.bound = -self._heap[0]

    def run(self, alive: int, cover: int, size: int, fsum: int) -> None:
        if not self.complete:
            return
        self.nodes += 1
        if self.nodes > ENUM_NODE_CAP or len(self.found) > ENUM_COVER_CAP or (
                self.deadline is not None and (self.nodes & 255) == 0 and time.perf_counter() > self.deadline):
            self.complete = False
            return
        adj = self.adj
        for v in _bits(alive):
            if adj[v] & alive == 0:
                alive &= ~(1 << v)
        if size > self.k or fsum > self.bound:
            return
        if alive == 0:
            if size == self.k:
                self._record(cover)
            return
        need = self.k - size
        # 下界（大きさ）：極大マッチングの本数
        if size + _matching_lb(alive, adj, self._ones) > self.k:
            return
        # 下界（手間）：あと need 個は要るので、残りの中で軽い方から need 個の和
        if need > 0:
            rest = sorted(self.freq[v] for v in _bits(alive))
            if fsum + sum(rest[:need]) > self.bound:
                return
        # 分枝：次数最大の頂点 u（同点は添字が小さい方）。u を入れる／u を入れず隣を全部入れる
        u = max(_bits(alive), key=lambda x: (_popcount(adj[x] & alive), -x))
        nb = adj[u] & alive
        self.run(alive & ~(1 << u), cover | (1 << u), size + 1, fsum + self.freq[u])
        self.run(alive & ~(1 << u) & ~nb, cover | nb, size + _popcount(nb), fsum + sum(self.freq[v] for v in _bits(nb)))


# ---------------------------------------------------------------- 貪欲（v1 と同じ）
def _greedy(inst: Instance) -> list[int]:
    """残る道を最も多く断つ道具を順に取る（同点は frequency が小さい方、さらに同点は添字順）。
    返り値は**選んだ順**の添字（v1 はこの順で primary を出す。報告のバイト一致のため同じにする）。"""
    n = inst.n
    masks = sorted({sum(1 << i for i in s) for s in inst.sets})
    remaining = list(masks)
    chosen: list[int] = []
    while remaining:
        best = max(range(n), key=lambda i: (sum(1 for pm in remaining if pm & (1 << i)), -inst.freq[i]))
        chosen.append(best)
        remaining = [pm for pm in remaining if not pm & (1 << best)]
    return chosen


# ---------------------------------------------------------------- 解く
@dataclass(frozen=True)
class Solution:
    cost: int
    cover: int
    method: str


def _optimum(inst: Instance, w: Sequence[int], forced_in: int, forced_out: int,
             deadline: Optional[float]) -> Solution:
    """制約付きの最適解（重み最小）。矛盾は Infeasible、時間切れは Timeout。"""
    res = _reduce(inst, forced_in, forced_out)
    base = sum(w[v] for v in _bits(res.forced))
    if res.alive == 0:
        return Solution(base, res.forced, "trivial")
    bip = _is_bipartite(res.alive, res.adj)
    if bip is not None:
        cost, cover = _bipartite_cover(res, bip[0], bip[1], w)
        return Solution(base + cost, res.forced | cover, "bipartite-konig")
    bb = _BB(res.adj, w, deadline)
    bb.run(res.alive, 0, 0)
    return Solution(base + bb.best_cost, res.forced | bb.best_cover, "branch-and-bound")


def _seq_key(inst: Instance, cover: int) -> list[str]:
    return [inst.ids[i] for i in _bits(cover)]


def _lexmin_by_oracle(inst: Instance, w: Sequence[int], opt_cost: int, k: int, deadline: Optional[float]) -> int:
    """(大きさ, 手間) が最適な被覆のうち v1 の鍵（id を並び順に並べた列の辞書順）で最小のものを、
    制約付きの再解で位置ごとに決める。"""
    n = inst.n
    prefix = 0
    last = -1
    for _pos in range(k):
        chosen = None
        for j in sorted(range(last + 1, n), key=lambda i: inst.ids[i]):
            fin = prefix | (1 << j)
            fout = ((1 << j) - 1) & ~prefix  # j より前で prefix に無い頂点は入れない
            try:
                sol = _optimum(inst, w, fin, fout, deadline)
            except Infeasible:
                continue
            if sol.cost == opt_cost:
                chosen = j
                break
        if chosen is None:  # 起きないはず（最適解は存在する）
            raise AssertionError("lexmin: 続きが見つからない")
        prefix |= 1 << chosen
        last = chosen
    return prefix


def solve(inst: Instance, *, exact_limit: int = 20, max_alternatives: int = 5,
          time_budget_s: float = 5.0) -> tuple[Checkpoints, dict[str, object]]:
    """Checkpoints と、報告向けの補足（列挙の打ち切り・節の数など）。"""
    notes: dict[str, object] = {"enum_complete": True, "tiebreak": "enumeration"}
    n = inst.n
    if not inst.sets:
        return Checkpoints(True, (), (), "trivial", 0), notes
    big = sum(inst.freq) + 1
    w = [big + f for f in inst.freq]
    deadline: Optional[float] = None
    if n > exact_limit:
        if time_budget_s <= 0:
            return _greedy_result(inst, w, notes), notes
        deadline = time.perf_counter() + time_budget_s
    try:
        sol = _optimum(inst, w, 0, 0, deadline)
    except Timeout:
        notes["timeout"] = "optimum"
        return _greedy_result(inst, w, notes), notes
    k, _f = divmod(sol.cost, big)
    # 同じ大きさの被覆を列挙 → 第一案と代替案
    res = _reduce(inst)
    en = _Enum(res.adj, inst.freq, k - _popcount(res.forced), max_alternatives + 1, deadline)
    en.run(res.alive, 0, 0, 0)
    covers = [res.forced | c for c in en.found]
    if en.complete:
        ranked = sorted(set(covers), key=lambda c: (sum(w[i] for i in _bits(c)), _seq_key(inst, c)))
        primary = ranked[0]
        assert sum(w[i] for i in _bits(primary)) == sol.cost
    else:
        notes["enum_complete"] = False
        notes["tiebreak"] = "oracle"
        try:
            primary = _lexmin_by_oracle(inst, w, sol.cost, k, deadline)
        except Timeout:
            notes["timeout"] = "tiebreak"
            primary = sol.cover
            notes["tiebreak"] = "first-found"
        ranked = sorted(set(covers) | {primary}, key=lambda c: (sum(w[i] for i in _bits(c)), _seq_key(inst, c)))
    alts = [c for c in ranked if c != primary][:max_alternatives]
    notes["enum_nodes"] = en.nodes
    notes["covers_enumerated"] = len(covers)
    return Checkpoints(True, tuple(_seq_key(inst, primary)), tuple(tuple(_seq_key(inst, c)) for c in alts),
                       sol.method, k), notes


def _greedy_result(inst: Instance, w: Sequence[int], notes: dict[str, object]) -> Checkpoints:
    res = _reduce(inst)
    lb = _popcount(res.forced) + _matching_lb(res.alive, res.adj, [1] * inst.n)
    chosen = _greedy(inst)
    size = len(chosen)
    notes["tiebreak"] = "greedy"
    return Checkpoints(size == lb, tuple(inst.ids[i] for i in chosen), (), "greedy", lb)


__all__ = ["Instance", "make_instance", "solve", "Timeout", "Infeasible", "ENUM_NODE_CAP", "ENUM_COVER_CAP"]
