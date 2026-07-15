"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { MessageCircle, X, Send } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface ChatWidgetProps {
  contextText: string; // summary of current results to give AI context
  apiKey?: string;     // frontend can also use OpenAI directly for chat
}

export function ChatWidget({ contextText }: ChatWidgetProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("https://api.openai.com/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${process.env.NEXT_PUBLIC_OPENAI_API_KEY || ""}`,
        },
        body: JSON.stringify({
          model: "gpt-4o-mini",
          messages: [
            {
              role: "system",
              content: `You are a tea packaging optimization assistant. You are helping a user understand their packaging optimization results. Here is the context of their current simulation:\n\n${contextText}\n\nAnswer questions helpfully and concisely. Use ₹ for INR. Keep answers under 3 sentences unless the user asks for detail.`,
            },
            { role: "user", content: text },
          ],
          max_tokens: 300,
          temperature: 0.5,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error?.message || `API error ${res.status}`);
      }

      const data = await res.json();
      const reply: Message = {
        role: "assistant",
        content: data.choices[0].message.content,
      };
      setMessages((prev) => [...prev, reply]);
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Sorry, I couldn't process that: ${e.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {/* Floating button */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 bg-primary text-primary-foreground rounded-full p-4 shadow-lg hover:bg-primary/90 transition-all"
          aria-label="Open AI Chat"
        >
          <MessageCircle className="h-5 w-5" />
        </button>
      )}

      {/* Chat panel */}
      {open && (
        <div className="fixed bottom-6 right-6 z-50 w-80 h-96 bg-card border rounded-lg shadow-xl flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b bg-primary text-primary-foreground rounded-t-lg">
            <span className="font-semibold text-sm flex items-center gap-2">
              <MessageCircle className="h-4 w-4" /> AI Assistant
            </span>
            <button onClick={() => setOpen(false)} className="hover:opacity-80">
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2 text-sm">
            {messages.length === 0 && (
              <p className="text-muted-foreground text-xs text-center py-8">
                Ask me anything about these optimization results — try "What if I switch to plastic?" or "Explain why 40HC was chosen."
              </p>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={`rounded-lg px-3 py-2 max-w-[85%] ${
                  m.role === "user"
                    ? "bg-primary text-primary-foreground ml-auto"
                    : "bg-muted text-foreground"
                }`}
              >
                {m.content}
              </div>
            ))}
            {loading && (
              <div className="bg-muted rounded-lg px-3 py-2 max-w-[85%]">
                <Spinner size="sm" />
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <form
            onSubmit={(e) => { e.preventDefault(); send(); }}
            className="flex items-center gap-2 p-3 border-t"
          >
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your results…"
              className="h-8 text-xs"
              disabled={loading}
            />
            <Button type="submit" size="icon" className="h-8 w-8" disabled={loading || !input.trim()}>
              <Send className="h-3 w-3" />
            </Button>
          </form>
        </div>
      )}
    </>
  );
}
