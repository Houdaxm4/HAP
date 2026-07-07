import type { AnalysisDetail } from "@/lib/types";

const sheetStatusStyles = {
  synced: "text-hap-success",
  pending: "text-hap-warning",
  error: "text-red-400",
};

export default function WorkbookTab({ analysis }: { analysis: AnalysisDetail }) {
  return (
    <div className="overflow-hidden rounded border border-hap-border bg-hap-panel">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-hap-border text-left text-xs uppercase tracking-wider text-hap-muted">
            <th className="px-4 py-3 font-medium">Sheet</th>
            <th className="px-4 py-3 font-medium">Rows</th>
            <th className="px-4 py-3 font-medium">Last Updated</th>
            <th className="px-4 py-3 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {analysis.workbookSheets.map((sheet) => (
            <tr
              key={sheet.name}
              className="border-b border-hap-border/50 hover:bg-hap-panel-elevated/50"
            >
              <td className="px-4 py-3 font-medium">{sheet.name}</td>
              <td className="px-4 py-3 font-mono text-hap-muted">{sheet.rows}</td>
              <td className="px-4 py-3 text-hap-muted">{sheet.lastUpdated}</td>
              <td className={`px-4 py-3 capitalize ${sheetStatusStyles[sheet.status]}`}>
                {sheet.status}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
