import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-4 bg-background">
      <h1 className="text-2xl font-semibold">Analysis not found</h1>
      <p className="text-sm text-hap-muted">
        The requested analysis does not exist.
      </p>
      <Link
        href="/"
        className="rounded border border-hap-orange/40 bg-hap-orange/10 px-4 py-2 text-sm font-medium text-hap-orange hover:bg-hap-orange/20"
      >
        Back to Command Center
      </Link>
    </div>
  );
}
