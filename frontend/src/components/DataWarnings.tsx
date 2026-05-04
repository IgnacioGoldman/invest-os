type Props = {
  warnings: string[];
};

export function DataWarnings({ warnings }: Props) {
  if (warnings.length === 0) {
    return null;
  }

  return (
    <section className="warnings">
      <h2>Data Warnings</h2>
      <ul>
        {warnings.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
    </section>
  );
}
