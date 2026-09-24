import pytest

from app.greenwave import (
    compute_max_coverage,
    compute_windows,
    departure_windows_for_intersection,
    eroded_green_components,
    intersect_interval_lists,
    local_green_intervals,
    merge_intervals,
)


def it(name=None, **kw):
    # 默认 green_start == green_end 表示整周期常绿，所有取值均满足 schema 约束。
    return {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 0, "travel": 0, **kw}


# ---------- 本地绿灯展开 ----------

def test_local_green_normal():
    assert local_green_intervals(60, 10, 30) == [[10, 30]]


def test_local_green_wrapping():
    assert local_green_intervals(60, 50, 10) == [[50, 60], [0, 10]]


def test_local_green_full_cycle():
    assert local_green_intervals(60, 20, 20) == [[0, 60]]


def test_merge_adjacent_half_open_intervals():
    assert merge_intervals([[0, 10], [10, 20]]) == [[0, 20]]
    assert merge_intervals([[5, 9], [0, 3], [3, 5]]) == [[0, 9]]
    assert merge_intervals([[0, 5], [6, 7]]) == [[0, 5], [6, 7]]


def test_intersection_basic():
    assert intersect_interval_lists([[0, 100]], [[20, 50], [60, 80]]) == [
        [20, 50],
        [60, 80],
    ]
    assert intersect_interval_lists([[0, 5]], [[5, 10]]) == []


# ---------- 单路口周期展开 ----------

def test_single_plain_window_clipped():
    # 全周期常绿：整个发车范围都可行
    got = departure_windows_for_intersection(60, 0, 0, 60, 0, 0, 600)
    assert got == [[0, 600]]


def test_single_periodic_green_and_offset():
    # [20,40) 绿灯，无偏移：在 [0,180) 内应出现 3 段
    got = departure_windows_for_intersection(60, 0, 20, 40, 0, 0, 180)
    assert got == [[20, 40], [80, 100], [140, 160]]


def test_offset_shifts_departure_window():
    # 偏移 10：本地相位 (t+10)%60 ∈ [20,40) ⇔ t%60 ∈ [10,30)
    got = departure_windows_for_intersection(60, 10, 20, 40, 0, 0, 120)
    assert got == [[10, 30], [70, 90]]


def test_travel_time_shifts_departure_window():
    # 行驶 15：t+15 落在 [20,40) ⇔ t ∈ [5,25)
    got = departure_windows_for_intersection(60, 0, 20, 40, 15, 0, 60)
    assert got == [[5, 25]]


def test_wrapping_green_unwrapped_across_boundary():
    # 绿灯 [50,60)∪[0,10)，行驶 0：可行段 [-10,10) 周期 60，裁剪到 [0,130)
    got = departure_windows_for_intersection(60, 0, 50, 10, 0, 0, 130)
    assert got == [[0, 10], [50, 70], [110, 130]]


def test_wrapping_green_with_travel():
    # 行驶 5：到达相位 (t+5)%60 ∈ [50,10)（绕零点）
    # 出发段：[-15,5) 周期 60，裁剪到 [0,125)
    got = departure_windows_for_intersection(60, 0, 50, 10, 5, 0, 125)
    assert got == [[0, 5], [45, 65], [105, 125]]


def test_range_starts_mid_cycle():
    got = departure_windows_for_intersection(60, 0, 0, 30, 0, 75, 150)
    # [0,30) 周期 60：[60,90) 裁剪为 [75,90)，另有 [120,150)
    assert got == [[75, 90], [120, 150]]


def test_green_equal_to_range_boundary_yields_empty():
    # 可行段恰好在发车范围起点“之后才开始”的反例：范围 [40,80)，绿灯 [20,40)
    got = departure_windows_for_intersection(60, 0, 20, 40, 0, 40, 80)
    assert got == []  # [20,40) 与范围无交；下一段 [80,100) 也无交


# ---------- 多路口联动（端到端，含暴力对照） ----------

# 下游路口相位偏移 30 秒，恰好补偿 30 秒行程，两路口可行域完全重合
TWO_NODES = [
    it(cycle=60, offset=0, green_start=0, green_end=30, travel=0),
    it(cycle=60, offset=30, green_start=0, green_end=30, travel=30),
]


def test_two_intersections_green_band():
    got = compute_windows(TWO_NODES, 0, 300)
    assert got == [[0, 30], [60, 90], [120, 150], [180, 210], [240, 270]]


def test_empty_array_when_no_solution():
    nodes = [
        it(cycle=60, green_start=0, green_end=10, travel=0),
        it(cycle=60, green_start=20, green_end=30, travel=0),
    ]
    assert compute_windows(nodes, 0, 60) == []


def test_eight_intersections_allowed():
    nodes = [it(travel=i * 5) for i in range(8)]  # 全周期常绿
    assert compute_windows(nodes, 100, 400) == [[100, 400]]


def test_half_open_endpoints_are_never_green():
    # 绿灯终点 30 不含：t=30 到达为红灯
    got = departure_windows_for_intersection(60, 0, 20, 30, 0, 20, 31)
    assert got == [[20, 30]]  # 30 不被包含


# ---------- 行驶时间波动 [travel, travel_max] ----------

def test_eroded_components_plain_green():
    # 普通绿灯 [20,40)：波动 10 秒后收缩为 [20,30)
    assert eroded_green_components(60, 20, 40, 10) == (False, [[20, 30]])
    # 波动量恰好等于绿灯长度：整条被吃掉
    assert eroded_green_components(60, 20, 40, 20) == (False, [])
    assert eroded_green_components(60, 20, 40, 25) == (False, [])


def test_eroded_components_wrapping_green_is_continuous_first():
    # 跨零点连续时段 [50,70)：先视为整体再收缩，不会被拆成两段
    assert eroded_green_components(60, 50, 10, 10) == (False, [[50, 60]])
    assert eroded_green_components(60, 50, 10, 20) == (False, [])


def test_eroded_components_always_green_unaffected():
    # 常绿：无论波动多大都不受影响
    assert eroded_green_components(60, 20, 20, 100) == (True, [])


def test_fluctuation_shrinks_plain_window():
    # 绿灯 [20,40)，行驶时间可能取 [0,10] 任意实数：
    # 需 t 与 t+10 均在绿灯半开区间内 ⇔ t ∈ [20,30)
    got = departure_windows_for_intersection(
        60, 0, 20, 40, 0, 0, 180, travel_max=10
    )
    assert got == [[20, 30], [80, 90], [140, 150]]


def test_fluctuation_continuous_wrapping_window():
    # 跨零点绿灯 [50,60)∪[0,10)，行驶时间可能取 [0,10]：
    # 连续时段 [50,70) 收缩为 [50,60)，shift=0 ⇔ 出发段 [50,60) 周期 60
    got = departure_windows_for_intersection(
        60, 0, 50, 10, 0, 0, 130, travel_max=10
    )
    assert got == [[50, 60], [110, 120]]


def test_fluctuation_equals_green_length_yields_empty():
    # 绿灯 20 秒、波动也是 20 秒：没有任何整数出发时刻能保证全程遇绿
    got = departure_windows_for_intersection(
        60, 0, 20, 40, 0, 0, 120, travel_max=20
    )
    assert got == []


def test_always_green_unaffected_by_fluctuation():
    got = departure_windows_for_intersection(
        60, 0, 0, 0, 0, 10, 200, travel_max=300
    )
    assert got == [[10, 200]]


def test_travel_max_defaults_to_travel():
    # 省略 travel_max 时与固定行驶时间完全一致
    with_max = departure_windows_for_intersection(
        60, 10, 20, 40, 5, 0, 120, travel_max=5
    )
    without = departure_windows_for_intersection(
        60, 10, 20, 40, 5, 0, 120
    )
    assert with_max == without == [[5, 25], [65, 85]]


def test_compute_windows_with_fluctuation_multi_intersection():
    # 路口 1：绿灯 [0,40) 无波动 ⇔ 出发段 [0,40) 周期 60
    # 路口 2：绿灯 [0,50)、偏移 10、行驶 [10,20]（slack=10）
    #   抵达相位区间 [t+20, t+30] 须整体落入某个 [60q, 60q+50)
    #   ⇔ t ∈ [60q-20, 60q+20)，在 [0,120) 内为 [0,20) [40,80) [100,120)
    # 两路口交集：[0,20) 与 [60,80)
    nodes = [
        it(cycle=60, green_start=0, green_end=40, travel=0),
        it(cycle=60, offset=10, green_start=0, green_end=50,
           travel=10, travel_max=20),
    ]
    assert compute_windows(nodes, 0, 120) == [[0, 20], [60, 80]]

    # 路口 2 绿灯缩短为 [0,20)：收缩后仅 [0,10)，出发段 [60q-20,60q-10)
    # 即 [40,50) [100,110)，与路口1 的 [0,40) [60,100) 无交集
    nodes[1] = it(cycle=60, offset=10, green_start=0, green_end=20,
                  travel=10, travel_max=20)
    assert compute_windows(nodes, 0, 120) == []


def test_brute_force_equivalence_on_random_cases():
    """与逐秒判定的参考实现完全一致（测试本身才允许逐秒）。"""
    import random

    random.seed(42)

    def brute(nodes, lo, hi):
        """逐秒参考实现：行驶时间取 [travel, travel_max] 内任意实数时，
        整数出发时刻 t 可行 ⇔ 抵达闭区间 [t+T, t+Tmax] 整体落在展开时间轴的
        某个绿灯半开分量内（常绿始终可行）。"""
        expected = []
        run_start = None
        for t in range(lo, hi + 1):
            ok = t < hi
            if ok:
                for n in nodes:
                    tmax = n.get("travel_max", n["travel"])
                    arrive_lo = t + n["travel"] + n["offset"]
                    arrive_hi = t + tmax + n["offset"]
                    gs, ge, c = n["green_start"], n["green_end"], n["cycle"]
                    if gs == ge:
                        contained = True
                    else:
                        contained = False
                        q0 = arrive_lo // c - 2
                        for q in range(q0, q0 + 6):
                            if gs < ge:
                                comp = (q * c + gs, q * c + ge)
                            else:  # 跨零点：连续分量 [qC+gs, (q+1)C+ge)
                                comp = (q * c + gs, (q + 1) * c + ge)
                            if comp[0] <= arrive_lo and arrive_hi < comp[1]:
                                contained = True
                                break
                    if not contained:
                        ok = False
                        break
            if ok:
                if run_start is None:
                    run_start = t
            else:
                if run_start is not None:
                    expected.append([run_start, t])
                    run_start = None
        if run_start is not None:
            expected.append([run_start, hi])
        return expected

    for _ in range(400):
        n_nodes = random.randint(1, 8)
        nodes = []
        for _ in range(n_nodes):
            c = random.randint(1, 90)
            gs = random.randint(0, c - 1)
            ge = random.randint(0, c - 1)
            travel = random.randint(0, 120)
            kwargs = dict(
                cycle=c,
                offset=random.randint(0, c - 1),
                green_start=gs,
                green_end=ge,
                travel=travel,
            )
            # 约一半用例带行驶时间波动；slack 偶尔超过绿灯长度甚至周期
            if random.random() < 0.5:
                kwargs["travel_max"] = travel + random.randint(0, 30)
            nodes.append(it(**kwargs))
        length = random.randint(1, 600)
        lo = random.randint(0, 300)
        hi = lo + length
        assert compute_windows(nodes, lo, hi) == brute(nodes, lo, hi)


# ---------- 最大覆盖路口数（端点差分扫描） ----------

def test_max_coverage_single_intersection():
    # 单路口绿灯 [20,40) 周期 60：覆盖 1 的段即其可行窗口，其余处为 0
    nodes = [it(cycle=60, green_start=20, green_end=40, travel=0)]
    maximum, intervals = compute_max_coverage(nodes, 0, 140)
    assert maximum == 1
    assert intervals == [[20, 40], [80, 100]]


def test_max_coverage_zero_when_never_feasible():
    # 波动量吃掉整条绿灯：没有任何可行时刻，最大值 0，仍返回完整发车范围
    nodes = [it(cycle=60, green_start=20, green_end=40, travel=0, travel_max=25)]
    maximum, intervals = compute_max_coverage(nodes, 30, 90)
    assert maximum == 0
    assert intervals == [[30, 90]]


def test_max_coverage_zero_windows_have_empty_interiors():
    # 两个路口各自可行但互不交叠：覆盖数最大 1；0 段不作为最优输出
    nodes = [
        it(cycle=60, green_start=0, green_end=10, travel=0),
        it(cycle=60, green_start=20, green_end=30, travel=0),
    ]
    maximum, intervals = compute_max_coverage(nodes, 0, 60)
    assert maximum == 1
    assert intervals == [[0, 10], [20, 30]]


def test_max_coverage_merges_adjacent_optimal_segments():
    # 路口 A 可行 [0,10)，路口 B 可行 [10,20)：10 处覆盖数恒为 1
    # （A 的 -1 与 B 的 +1 在同一端点相消），两段须合并为 [0,20)
    nodes = [
        it(cycle=60, green_start=0, green_end=10, travel=0),
        it(cycle=60, green_start=10, green_end=20, travel=0),
    ]
    maximum, intervals = compute_max_coverage(nodes, 0, 60)
    assert maximum == 1
    assert intervals == [[0, 20]]


def test_max_coverage_overlapping_pairs():
    # A: [0,30)；B: [20,50)。覆盖数：[0,20)->1，[20,30)->2，[30,50)->1
    nodes = [
        it(cycle=60, green_start=0, green_end=30, travel=0),
        it(cycle=60, green_start=20, green_end=50, travel=0),
    ]
    maximum, intervals = compute_max_coverage(nodes, 0, 60)
    assert maximum == 2
    assert intervals == [[20, 30]]


def test_max_coverage_all_green_and_periodic_mix():
    # 常绿路口处处 +1；周期路口可行 [10,20) 时覆盖 2，其余处为 1
    nodes = [
        it(cycle=60, green_start=0, green_end=0, travel=0),
        it(cycle=60, green_start=10, green_end=20, travel=0),
    ]
    maximum, intervals = compute_max_coverage(nodes, 0, 60)
    assert maximum == 2
    assert intervals == [[10, 20]]


def test_max_coverage_all_always_green_covers_whole_range():
    nodes = [it(travel=i) for i in range(3)]
    maximum, intervals = compute_max_coverage(nodes, 100, 400)
    assert maximum == 3
    assert intervals == [[100, 400]]


def test_max_coverage_wrapping_green_adjacent_repetitions_merge():
    # 跨零点绿灯 [50,60)∪[0,10)，行驶 5：可行段 [45,65) 是连续的一段
    # （周期展开后两端相接已由单路口窗口合并），覆盖 1 即该段
    nodes = [it(cycle=60, green_start=50, green_end=10, travel=5)]
    maximum, intervals = compute_max_coverage(nodes, 0, 125)
    assert maximum == 1
    assert intervals == [[0, 5], [45, 65], [105, 125]]


def test_max_coverage_clipped_to_range_boundaries():
    # 可行段 [-15,5)/[45,65)/[105,125)：范围落在两段之间时覆盖数为 0
    nodes = [it(cycle=60, green_start=50, green_end=10, travel=5)]
    maximum, intervals = compute_max_coverage(nodes, 30, 45)
    assert maximum == 0
    assert intervals == [[30, 45]]
    # 范围与可行段部分相交时按半开边界裁剪
    maximum, intervals = compute_max_coverage(nodes, 47, 50)
    assert maximum == 1
    assert intervals == [[47, 50]]
    # 范围恰好在可行段左端点结束：[30,45) 与 [45,65) 无交（45 不含）
    maximum, intervals = compute_max_coverage(nodes, 30, 46)
    assert (maximum, intervals) == (1, [[45, 46]])


def test_max_coverage_with_travel_max_fluctuation():
    # 绿灯 [20,40)、行驶 [0,10]：单路口收缩为 [20,30)，覆盖 1 仅在收缩段
    nodes = [
        it(cycle=60, green_start=20, green_end=40, travel=0, travel_max=10)
    ]
    maximum, intervals = compute_max_coverage(nodes, 0, 120)
    assert maximum == 1
    assert intervals == [[20, 30], [80, 90]]


def test_max_coverage_three_nodes_step_profile():
    # A: [0,40)；B: [10,30)；C: [20,50)，周期 60
    # 覆盖：[0,10)->1 [10,20)->2 [20,30)->3 [30,40)->2 [40,50)->1
    nodes = [
        it(cycle=60, green_start=0, green_end=40, travel=0),
        it(cycle=60, green_start=10, green_end=30, travel=0),
        it(cycle=60, green_start=20, green_end=50, travel=0),
    ]
    maximum, intervals = compute_max_coverage(nodes, 0, 60)
    assert maximum == 3
    assert intervals == [[20, 30]]


def test_max_coverage_multiple_disjoint_maximum_segments():
    # 三路口每周期均在 [0,10) 可行；最大 3 的段在范围内出现两次，不合并
    nodes = [
        it(cycle=60, offset=0, green_start=0, green_end=10, travel=0),
        it(cycle=60, offset=0, green_start=0, green_end=10, travel=0),
        it(cycle=60, offset=0, green_start=0, green_end=10, travel=0),
    ]
    maximum, intervals = compute_max_coverage(nodes, 0, 130)
    assert maximum == 3
    assert intervals == [[0, 10], [60, 70], [120, 130]]


def test_max_coverage_brute_force_equivalence_on_random_cases():
    """与逐秒统计覆盖数的参考实现完全一致（测试本身才允许逐秒）。"""
    import random

    random.seed(7)

    def brute(nodes, lo, hi):
        best = -1
        best_intervals = []
        run_start = None
        for t in range(lo, hi):
            count = 0
            for n in nodes:
                tmax = n.get("travel_max", n["travel"])
                arrive_lo = t + n["travel"] + n["offset"]
                arrive_hi = t + tmax + n["offset"]
                gs, ge, c = n["green_start"], n["green_end"], n["cycle"]
                if gs == ge:
                    count += 1
                    continue
                q0 = arrive_lo // c - 2
                for q in range(q0, q0 + 6):
                    if gs < ge:
                        comp = (q * c + gs, q * c + ge)
                    else:
                        comp = (q * c + gs, (q + 1) * c + ge)
                    if comp[0] <= arrive_lo and arrive_hi < comp[1]:
                        count += 1
                        break
            if count > best:
                best = count
                best_intervals = [[t, t + 1]]
                run_start = t
            elif count == best:
                if run_start is not None:
                    best_intervals[-1][1] = t + 1
                else:
                    best_intervals.append([t, t + 1])
                    run_start = t
            else:
                run_start = None
        return best, best_intervals

    for _ in range(400):
        n_nodes = random.randint(1, 8)
        nodes = []
        for _ in range(n_nodes):
            c = random.randint(1, 90)
            gs = random.randint(0, c - 1)
            ge = random.randint(0, c - 1)
            travel = random.randint(0, 120)
            kwargs = dict(
                cycle=c,
                offset=random.randint(0, c - 1),
                green_start=gs,
                green_end=ge,
                travel=travel,
            )
            if random.random() < 0.5:
                kwargs["travel_max"] = travel + random.randint(0, 30)
            nodes.append(it(**kwargs))
        length = random.randint(1, 600)
        lo = random.randint(0, 300)
        hi = lo + length
        assert compute_max_coverage(nodes, lo, hi) == brute(nodes, lo, hi)
