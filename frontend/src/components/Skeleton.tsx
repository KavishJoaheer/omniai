/**
 * Skeleton loading placeholder — shows an animated pulse while data loads.
 *
 * Usage:
 *   <Skeleton />               // single line
 *   <Skeleton width="60%" />   // shorter line
 *   <Skeleton height="80px" /> // block
 *   <SkeletonTable rows={4} cols={3} />
 *   <SkeletonCard />
 */

interface SkeletonProps {
  width?: string;
  height?: string;
  style?: React.CSSProperties;
}

export function Skeleton({ width = "100%", height = "14px", style }: SkeletonProps) {
  return (
    <span
      className="skeleton"
      aria-hidden="true"
      style={{ width, height, display: "block", borderRadius: 6, ...style }}
    />
  );
}

export function SkeletonTable({ rows = 4, cols = 3 }: { rows?: number; cols?: number }) {
  return (
    <div className="table-wrap" aria-busy="true" aria-label="Loading…">
      <table>
        <thead>
          <tr>
            {Array.from({ length: cols }).map((_, i) => (
              <th key={i}><Skeleton width="70%" /></th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: cols }).map((_, c) => (
                <td key={c}><Skeleton width={c === 0 ? "80%" : "55%"} /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SkeletonCard() {
  return (
    <article className="metric-card" aria-busy="true" aria-label="Loading…">
      <Skeleton width="50%" height="11px" />
      <Skeleton width="40%" height="20px" style={{ marginTop: 6 }} />
    </article>
  );
}

export function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div className="stack" aria-busy="true" aria-label="Loading…">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Skeleton width="24px" height="24px" style={{ borderRadius: "50%", flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            <Skeleton width="65%" height="13px" />
            <Skeleton width="40%" height="11px" style={{ marginTop: 5 }} />
          </div>
        </div>
      ))}
    </div>
  );
}
