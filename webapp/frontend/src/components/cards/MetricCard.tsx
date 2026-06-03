interface Props {
  label: string;
  value: string | number | null | undefined;
  unit?: string;
  secondary?: string;
  accent?: "default" | "green" | "red" | "yellow";
}

const accentClasses = {
  default: "border-gray-800",
  green: "border-green-600/50",
  red: "border-red-600/50",
  yellow: "border-yellow-600/50",
};

function fmt(v: unknown): string {
  if (v == null) return "\u2014";
  if (typeof v === "number") {
    if (Math.abs(v) < 0.001 && v !== 0) return v.toExponential(2);
    if (Math.abs(v) >= 1e6) return v.toExponential(2);
    return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return String(v);
}

export default function MetricCard({
  label,
  value,
  unit,
  secondary,
  accent = "default",
}: Props) {
  return (
    <div
      className={`rounded-xl border bg-gray-900/60 px-5 py-4 ${accentClasses[accent]}`}
    >
      <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold text-white">
        {fmt(value)}
        {unit && (
          <span className="ml-1 text-sm font-normal text-gray-500">
            {unit}
          </span>
        )}
      </p>
      {secondary && (
        <p className="mt-1 text-xs text-gray-500">{secondary}</p>
      )}
    </div>
  );
}
