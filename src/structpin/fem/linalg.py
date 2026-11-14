"""Dense linear algebra helpers (pure Python, no third-party dependencies)."""


class SingularSystemError(ArithmeticError):
    """Raised when a stiffness system is singular or numerically unstable."""


def solve_dense(A, b, rel_tol=1e-9):
    """Solve A x = b by Gaussian elimination with partial pivoting.

    A pivot whose magnitude is below rel_tol times the largest matrix entry
    is treated as zero, which usually means the structure is unstable or
    under-restrained.
    """
    n = len(b)
    if len(A) != n or any(len(row) != n for row in A):
        raise ValueError("A must be square and match the length of b")

    scale = max((abs(v) for row in A for v in row), default=0.0)
    if scale == 0.0:
        raise SingularSystemError("zero matrix")

    M = [[float(v) for v in row] + [float(b[i])] for i, row in enumerate(A)]

    for k in range(n):
        p = max(range(k, n), key=lambda r: abs(M[r][k]))
        if abs(M[p][k]) <= rel_tol * scale:
            raise SingularSystemError(
                f"pivot {k} is numerically zero; check supports and structural stability"
            )
        M[k], M[p] = M[p], M[k]
        pivot_row = M[k]
        pivot = pivot_row[k]
        for r in range(k + 1, n):
            row = M[r]
            f = row[k] / pivot
            if f != 0.0:
                for c in range(k, n + 1):
                    row[c] -= f * pivot_row[c]

    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = M[r][n] - sum(M[r][c] * x[c] for c in range(r + 1, n))
        x[r] = s / M[r][r]
    return x
