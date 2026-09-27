export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={`wordmark ${className ?? ""}`}>
      Oikonomos
      <sup>e-konomos</sup>
    </span>
  );
}
