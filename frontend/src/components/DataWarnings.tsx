type Props = {
  warnings: string[];
};

const splitSuggestion = (warning: string) => {
  const marker = " Suggested action: ";
  const [message, suggestion] = warning.split(marker);
  return { message, suggestion };
};

export function DataWarnings({ warnings }: Props) {
  if (warnings.length === 0) {
    return null;
  }

  return (
    <section className="warnings">
      <h2>Data Warnings</h2>
      <ul>
        {warnings.map((warning) => {
          const { message, suggestion } = splitSuggestion(warning);
          return (
            <li key={warning}>
              <span>{message}</span>
              {suggestion && <strong>Suggested action: {suggestion}</strong>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
