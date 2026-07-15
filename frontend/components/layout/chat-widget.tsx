"use client";

/**
 * AI assistant panel.
 *
 * This component deliberately holds no API key and talks to no third party. It
 * calls our own POST /api/chat, which proxies to OpenAI server-side.
 *
 * The previous version called api.openai.com directly using
 * NEXT_PUBLIC_OPENAI_API_KEY. Next.js inlines every NEXT_PUBLIC_* value into the
 * client bundle at build time, so that key was readable by anyone who opened
 * DevTools and spendable by anyone who copied it.
 */

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { MessageCircle, X, Send, Calculator } from "lucide-react";
import { sendChatMessage, type ChatMessage } from "@/lib/api";

interface ChatWidgetProps {
  /** Grounds answers in a stored simulation. The server loads the facts itself. */
  simulationId?: string;
}

interface DisplayMessage extends ChatMessage {
  /** True when the reply's numbers came from a real optimiser run, not the model. */
  computed?: boolean;
}

const SUGGESTIONS = [
  "What if I switch to plastic?",
  "Why was this container chosen?",
  "What if cartons must stay under 15kg?",
];

export function ChatWidget({ simulationId }: ChatWidgetProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || loading) return;

    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setInput("");
    setLoading(true);

    try {
      const res = await sendChatMessage({
        message: question,
        simulation_id: simulationId,
        history,
      });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.reply,
          computed: res.tool_calls.length > 0,
        },
      ]);
    } catch (e) {
      const detail = e instanceof Error ? e.message : "Unknown error";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Sorry — ${detail}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 bg-primary text-primary-foreground rounded-full p-4 shadow-lg hover:bg-primary/90 transition-all no-print"
          aria-label="Open AI assistant"
        >
          <MessageCircle className="h-5 w-5" />
        </button>
      )}

      {open && (
        <div
          role="dialog"
          aria-label="AI assistant"
          className="fixed bottom-6 right-6 z-50 w-80 h-[26rem] bg-card border rounded-lg shadow-xl flex flex-col no-print"
        >
          <div className="flex items-center justify-between px-4 py-3 border-b bg-primary text-primary-foreground rounded-t-lg">
            <span className="font-semibold text-sm flex items-center gap-2">
              <MessageCircle className="h-4 w-4" aria-hidden="true" /> AI Assistant
            </span>
            <button
              onClick={() => setOpen(false)}
              className="hover:opacity-80"
              aria-label="Close AI assistant"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-2 text-sm">
            {messages.length === 0 && (
              <div className="py-4 space-y-3">
                <p className="text-muted-foreground text-xs text-center">
                  Ask about these results. What-if questions re-run the real
                  optimiser rather than being estimated.
                </p>
                <div className="flex flex-col gap-1.5">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      className="text-xs text-left px-2.5 py-1.5 rounded border border-dashed hover:bg-muted transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <div
                key={i}
                className={`rounded-lg px-3 py-2 max-w-[85%] whitespace-pre-wrap ${
                  m.role === "user"
                    ? "bg-primary text-primary-foreground ml-auto"
                    : "bg-muted text-foreground"
                }`}
              >
                {m.content}
                {m.computed && (
                  <span
                    className="mt-1.5 flex items-center gap-1 text-[10px] text-muted-foreground"
                    title="These figures came from a live optimiser run"
                  >
                    <Calculator className="h-3 w-3" aria-hidden="true" />
                    Calculated by the optimiser
                  </span>
                )}
              </div>
            ))}

            {loading && (
              <div className="bg-muted rounded-lg px-3 py-2 max-w-[85%]">
                <Spinner size="sm" />
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="flex items-center gap-2 p-3 border-t"
          >
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your results…"
              className="h-8 text-xs"
              disabled={loading}
              aria-label="Message"
            />
            <Button
              type="submit"
              size="icon"
              className="h-8 w-8"
              disabled={loading || !input.trim()}
              aria-label="Send"
            >
              <Send className="h-3 w-3" />
            </Button>
          </form>
        </div>
      )}
    </>
  );
}
