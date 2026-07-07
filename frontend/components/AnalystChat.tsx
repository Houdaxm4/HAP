"use client";

import { useState } from "react";
import { getAnalystGreeting, getAnalystLabel } from "@/lib/app_config";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
};

export default function AnalystChat() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "initial",
      role: "assistant",
      content: getAnalystGreeting(),
      timestamp: "08:42 AM",
    },
  ]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed) return;

    const now = new Date().toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
    });

    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: "user", content: trimmed, timestamp: now },
      {
        id: `a-${Date.now()}`,
        role: "assistant",
        content:
          `I've noted your request. In production, this will route to the ${getAnalystLabel()} agent with full analysis context.`,
        timestamp: now,
      },
    ]);
    setInput("");
  };

  return (
    <aside className="flex h-full w-full flex-col border-t border-hap-border bg-hap-panel lg:w-80 lg:border-t-0 lg:border-l xl:w-96">
      <div className="flex shrink-0 items-center gap-3 border-b border-hap-border px-5 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-hap-orange to-hap-orange-dim text-xs font-bold text-black">
          AI
        </div>
        <div>
          <h3 className="text-sm font-semibold">{getAnalystLabel()}</h3>
          <p className="text-[10px] text-hap-muted">Investment intelligence</p>
        </div>
        <span className="ml-auto h-2 w-2 rounded-full bg-hap-success" />
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`max-w-[90%] rounded-lg px-4 py-3 ${
              msg.role === "assistant"
                ? "rounded-tl-none border border-hap-border bg-hap-panel-elevated"
                : "ml-auto rounded-tr-none border border-hap-orange/30 bg-hap-orange/10"
            }`}
          >
            <p className="whitespace-pre-line text-sm leading-relaxed text-foreground/90">
              {msg.content}
            </p>
            <p className="mt-2 text-[10px] text-hap-muted">{msg.timestamp}</p>
          </div>
        ))}
      </div>

      <div className="shrink-0 border-t border-hap-border p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Ask the analyst..."
            className="flex-1 rounded border border-hap-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-hap-muted focus:border-hap-orange/50 focus:outline-none focus:ring-1 focus:ring-hap-orange/30"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="shrink-0 rounded bg-hap-orange px-4 py-2.5 text-sm font-semibold text-black transition-colors hover:bg-hap-orange-dim disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </div>
    </aside>
  );
}
