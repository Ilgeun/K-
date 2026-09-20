"""평가용 통계: 비율의 Wilson 신뢰구간, 층화 표본의 전체 추정."""
from math import sqrt

Z = 1.959964   # 95%


def wilson(k: int, n: int, z: float = Z) -> tuple[float, float]:
    """정답 k / 표본 n 의 95% Wilson 구간. n=0 이면 (0, 1)."""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def stratified(strata: list[tuple[int, int, int]], z: float = Z) -> tuple[float, float, float]:
    """strata: (전체 개수 N_h, 검수한 수 n_h, 정답 수 k_h). 전체 정확도의 점추정과 근사 95% 구간(정규 근사, 유한모집단 보정 포함).
    표본이 작거나 정확도가 100%에 가까우면 구간이 좁게 나올 수 있어 참고용이다."""
    strata = [s for s in strata if s[1] > 0]           # 검수한 것이 없는 층은 추정에서 뺀다
    total = sum(N for N, _, _ in strata)
    if total == 0:
        return 0.0, 0.0, 1.0
    est = sum(N / total * (k / n) for N, n, k in strata)
    var = 0.0
    for N, n, k in strata:
        p = k / n
        fpc = 1 - n / N if N > 0 else 0
        var += (N / total) ** 2 * (p * (1 - p) / max(n - 1, 1)) * fpc
    h = z * sqrt(var)
    return est, max(0.0, est - h), min(1.0, est + h)
