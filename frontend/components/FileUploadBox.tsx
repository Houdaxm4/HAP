"use client";

import { useCallback, useRef, useState } from "react";

type FileUploadBoxProps = {
  label: string;
  description?: string;
  accept?: string;
  file: File | null;
  onFileChange: (file: File | null) => void;
};

export default function FileUploadBox({
  label,
  description,
  accept = ".xlsx,.xls,.csv",
  file,
  onFileChange,
}: FileUploadBoxProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const dropped = e.dataTransfer.files[0];
      if (dropped) onFileChange(dropped);
    },
    [onFileChange],
  );

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium uppercase tracking-wider text-hap-muted">
        {label}
      </label>

      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`group relative flex min-h-[88px] cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed px-4 py-4 transition-all ${
          isDragging
            ? "border-hap-orange bg-hap-orange/10"
            : file
              ? "border-hap-success/40 bg-hap-success/5"
              : "border-hap-border-bright bg-hap-panel-elevated/50 hover:border-hap-orange/40 hover:bg-hap-panel-elevated"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
        />

        {file ? (
          <div className="flex w-full items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded bg-hap-success/15 text-hap-success">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{file.name}</p>
              <p className="text-xs text-hap-muted">{formatSize(file.size)}</p>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onFileChange(null);
                if (inputRef.current) inputRef.current.value = "";
              }}
              className="shrink-0 rounded p-1 text-hap-muted transition-colors hover:bg-hap-border hover:text-foreground"
              aria-label="Remove file"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ) : (
          <>
            <svg className="mb-1.5 h-5 w-5 text-hap-muted transition-colors group-hover:text-hap-orange" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
            <p className="text-xs text-hap-muted">
              Drop file or <span className="text-hap-orange">browse</span>
            </p>
            {description && (
              <p className="mt-0.5 text-[10px] text-hap-muted/70">{description}</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
