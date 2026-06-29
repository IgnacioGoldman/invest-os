import { memo, useMemo } from "react";

type Props = {
  warnings: string[];
};

const splitSuggestion = (warning: string) => {
  const marker = " Suggested action: ";
  const [message, suggestion] = warning.split(marker);
  return { message, suggestion };
};

export const DataWarnings = memo(function DataWarnings({ warnings }: Props) {
  const rows = useMemo(() => warnings.map((warning) => ({ warning, ...splitSuggestion(warning) })), [warnings]);

  if (warnings.length === 0) {
    return null;
  }

  return (
    <section className="warnings">
      <h2>Data Warnings</h2>
      <ul>
        {rows.map(({ warning, message, suggestion }) => {
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
});
