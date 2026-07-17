import React, { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FiCpu, FiMessageCircle, FiSend, FiX, FiZap } from "react-icons/fi";
import ReactMarkdown from "react-markdown";
import { buildApiUrl, ensureCsrfToken } from "../api";
import { getErrorMessage } from "../utils/errorUtils";

interface ContractChatProps {
  isOpen: boolean;
  onClose: () => void;
  contractId: number;
  contractTitle: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}

const suggestions = [
  "Was sind die wichtigsten Kündigungsbedingungen?",
  "Fasse den Vertrag kurz zusammen.",
  "Welche Kosten und Verpflichtungen entstehen?",
];

const ContractChat: React.FC<ContractChatProps> = ({
  isOpen,
  onClose,
  contractId,
  contractTitle,
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const updateAssistant = (content: string, isStreaming = true) => {
    setMessages((current) => {
      const next = [...current];
      const index = next.length - 1;
      if (index >= 0 && next[index].role === "assistant")
        next[index] = { ...next[index], content, isStreaming };
      return next;
    });
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const question = input.trim();
    setInput("");
    setMessages((current) => [
      ...current,
      { role: "user", content: question },
      { role: "assistant", content: "", isStreaming: true },
    ]);
    setLoading(true);

    try {
      const csrfToken = await ensureCsrfToken();
      const response = await fetch(
        buildApiUrl(`/contracts/${contractId}/chat/stream`),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
          },
          body: JSON.stringify({ question }),
          credentials: "include",
        },
      );
      if (!response.ok)
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      const reader = response.body?.getReader();
      if (!reader) throw new Error("Keine Antwort vom Server");

      const decoder = new TextDecoder();
      let fullContent = "";
      let pending = "";
      const processEvent = (event: string) => {
        const dataLines = event
          .split("\n")
          .filter((line) => line.startsWith("data: "))
          .map((line) => line.slice(6));
        for (const jsonData of dataLines) {
          const data = JSON.parse(jsonData);
          if (data === "[DONE]") continue;
          if (typeof data === "string" && data.startsWith("[ERROR]"))
            throw new Error(data.slice(8));
          if (typeof data === "string") {
            fullContent += data;
            updateAssistant(fullContent);
          }
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        pending += decoder.decode(value, { stream: true });
        const events = pending.split("\n\n");
        pending = events.pop() ?? "";
        events.filter(Boolean).forEach(processEvent);
      }
      pending += decoder.decode();
      if (pending.trim()) processEvent(pending);
      updateAssistant(fullContent, false);
    } catch (error: unknown) {
      updateAssistant(
        `Die Anfrage konnte nicht beantwortet werden: ${getErrorMessage(error, "Unbekannter Fehler")}`,
        false,
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-[80] bg-black/60 backdrop-blur-sm"
          />
          <motion.aside
            initial={{ opacity: 0, x: 80 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 80 }}
            transition={{ duration: 0.24 }}
            className={[
              "fixed bottom-0 right-0 top-0 z-[90] flex w-full max-w-lg flex-col",
              "border-l border-white/[0.09] bg-[#0b0e0c]",
              "shadow-[-30px_0_100px_rgba(0,0,0,.5)]",
            ].join(" ")}
          >
            <header className="border-b border-white/[0.07] p-5">
              <div className="flex items-center justify-between">
                <div className="flex min-w-0 items-center gap-3">
                  <div
                    className={[
                      "flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border",
                      "border-[#977dff]/20 bg-[#977dff]/[0.08] text-[#c5b8ff]",
                    ].join(" ")}
                  >
                    <FiCpu size={20} />
                  </div>
                  <div className="min-w-0">
                    <p className="eyebrow">Document copilot</p>
                    <h2 className="mt-1 truncate text-base font-semibold">
                      {contractTitle}
                    </h2>
                  </div>
                </div>
                <button onClick={onClose} className="icon-btn shrink-0">
                  <FiX />
                </button>
              </div>
              <div className="mt-4 flex items-center gap-2 text-xs text-white/34">
                <span className="h-1.5 w-1.5 rounded-full bg-[#b8f15a] shadow-[0_0_10px_#b8f15a]" />{" "}
                Kontext ist auf dieses Dokument begrenzt
              </div>
            </header>

            <div className="flex-1 space-y-5 overflow-y-auto p-5">
              {!messages.length && (
                <div className="flex min-h-full flex-col justify-center py-8">
                  <div
                    className={[
                      "mx-auto flex h-14 w-14 items-center justify-center rounded-3xl border",
                      "border-white/[0.08] bg-white/[0.025] text-white/50",
                    ].join(" ")}
                  >
                    <FiMessageCircle size={24} />
                  </div>
                  <h3 className="mt-5 text-center text-xl font-semibold tracking-[-0.025em]">
                    Frag dein Dokument
                  </h3>
                  <p className="mx-auto mt-2 max-w-xs text-center text-sm leading-6 text-white/38">
                    Der Copilot liest den Vertragsinhalt und antwortet
                    ausschließlich auf Basis der vorhandenen Informationen.
                  </p>
                  <div className="mt-7 space-y-2">
                    {suggestions.map((suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() => setInput(suggestion)}
                        className={[
                          "surface-interactive flex w-full items-center gap-3 px-4 py-3 text-left",
                          "text-sm text-white/64",
                        ].join(" ")}
                      >
                        <FiZap className="shrink-0 text-[#b8f15a]" />{" "}
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((message, index) => (
                <div
                  key={index}
                  className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={[
                      "max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-6",
                      message.role === "user"
                        ? "rounded-br-md bg-[#b8f15a] text-[#10130c]"
                        : "rounded-bl-md border border-white/[0.08] bg-white/[0.035] text-white/74",
                    ].join(" ")}
                  >
                    {message.role === "user" ? (
                      <p className="whitespace-pre-wrap">{message.content}</p>
                    ) : (
                      <div
                        className={[
                          "prose prose-sm prose-invert max-w-none prose-headings:my-2 prose-p:my-1",
                          "prose-li:my-0 prose-ol:my-1 prose-ul:my-1 prose-pre:border",
                          "prose-pre:border-white/10 prose-pre:bg-black/30",
                        ].join(" ")}
                      >
                        <ReactMarkdown>{message.content}</ReactMarkdown>
                        {message.isStreaming && message.content && (
                          <span className="ml-1 inline-block h-4 w-1.5 animate-pulse bg-[#b8f15a]" />
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {loading && !messages[messages.length - 1]?.content && (
                <div className="flex justify-start">
                  <div
                    className={[
                      "flex gap-1 rounded-2xl rounded-bl-md border border-white/[0.08]",
                      "bg-white/[0.035] px-4 py-4",
                    ].join(" ")}
                  >
                    {[0, 1, 2].map((delay) => (
                      <span
                        key={delay}
                        className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#b8f15a]"
                        style={{ animationDelay: `${delay * 140}ms` }}
                      />
                    ))}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <footer className="border-t border-white/[0.07] bg-black/10 p-4">
              <div
                className={[
                  "flex items-end gap-2 rounded-2xl border border-white/[0.1]",
                  "bg-white/[0.025] p-2 focus-within:border-[#b8f15a]/35",
                ].join(" ")}
              >
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      handleSend();
                    }
                  }}
                  placeholder="Frage zum Vertrag stellen …"
                  disabled={loading}
                  rows={1}
                  className={[
                    "max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm",
                    "text-white placeholder:text-white/25 focus:outline-none",
                  ].join(" ")}
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || loading}
                  className={[
                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl",
                    "bg-[#b8f15a] text-[#10130c] transition-transform hover:scale-105",
                    "disabled:cursor-not-allowed disabled:opacity-35",
                  ].join(" ")}
                >
                  <FiSend />
                </button>
              </div>
              <p className="mt-2 text-center text-[10px] text-white/24">
                Antworten können Fehler enthalten. Wichtige Angaben im Original
                prüfen.
              </p>
            </footer>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
};

export default ContractChat;
