[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="Numeric division, cast rounding, and zero-divisor semantics" direction="—" kind=overview order=11 -->

# Numeric division, cast rounding, and zero-divisor semantics

Three related but distinct per-engine divergences around plain arithmetic,
gathered here because an aggregate divisor (`SUM(x)/COUNT(x)`) is the most
common place they surface, even though the compensation applies to any
division or cast, aggregate or not.
