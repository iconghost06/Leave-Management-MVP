export default function ErrorBanner({ error }) {
  if (!error) return null;
  return (
    <div className="error-banner" role="alert">
      {error.message}
      {error.code && <span className="error-code"> ({error.code})</span>}
    </div>
  );
}
