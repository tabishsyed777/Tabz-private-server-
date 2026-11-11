import { useEffect, useRef, useState } from "react";
import type { ReactNode, MouseEvent } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import "./history.css";
import "./markdown.css";

type Model = { name: string };
type MessageStatus = "streaming" | "complete" | "interrupted" | "error";
type Message = { id?: string; role: "user" | "assistant"; content: string; status?: MessageStatus; error_message?: string | null };
type Conversation = { id: string; title: string; model: string };
const api = import.meta.env.VITE_API_URL ?? "";

function InlineMarkdown({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return <>{parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*")) return <em key={index}>{part.slice(1, -1)}</em>;
    return <span key={index}>{part}</span>;
  })}</>;
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }
  return <div className="code-block"><div className="code-toolbar"><span>{language || "CODE"}</span><button onClick={() => void copy()}>{copied ? "Copied" : "Copy"}</button></div><pre><code>{code}</code></pre></div>;
}

function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index++; continue; }
    if (line.trim().startsWith("```")) {
      const language = line.trim().slice(3).trim();
      const code: string[] = [];
      index++;
      while (index < lines.length && !lines[index].trim().startsWith("```")) code.push(lines[index++]);
      if (index < lines.length) index++;
      blocks.push(<CodeBlock key={`code-${blocks.length}`} language={language} code={code.join("\n")} />);
      continue;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      const content = <InlineMarkdown text={heading[2]} />;
      const key = `heading-${blocks.length}`;
      blocks.push(heading[1].length === 1 ? <h2 key={key}>{content}</h2> : heading[1].length === 2 ? <h3 key={key}>{content}</h3> : <h4 key={key}>{content}</h4>);
      index++;
      continue;
    }
    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*[-*+]\s+/.test(lines[index])) items.push(lines[index++].replace(/^\s*[-*+]\s+/, ""));
      blocks.push(<ul key={`ul-${blocks.length}`}>{items.map((item, i) => <li key={i}><InlineMarkdown text={item} /></li>)}</ul>);
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) items.push(lines[index++].replace(/^\s*\d+[.)]\s+/, ""));
      blocks.push(<ol key={`ol-${blocks.length}`}>{items.map((item, i) => <li key={i}><InlineMarkdown text={item} /></li>)}</ol>);
      continue;
    }
    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) quote.push(lines[index++].replace(/^>\s?/, ""));
      blocks.push(<blockquote key={`quote-${blocks.length}`}><InlineMarkdown text={quote.join("\n")} /></blockquote>);
      continue;
    }
    const paragraph: string[] = [];
    while (index < lines.length && lines[index].trim() && !/^(#{1,3})\s+/.test(lines[index]) && !/^\s*[-*+]\s+/.test(lines[index]) && !/^\s*\d+[.)]\s+/.test(lines[index]) && !/^\s*```/.test(lines[index]) && !/^>\s?/.test(lines[index])) paragraph.push(lines[index++]);
    blocks.push(<p key={`p-${blocks.length}`}><InlineMarkdown text={paragraph.join("\n")} /></p>);
  }
  return <div className="markdown">{blocks}</div>;
}

function App() {
  const [models, setModels] = useState<Model[]>([]);
  const [model, setModel] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState("Checking local Ollama…");
  const [contextWindow, setContextWindow] = useState(4096);
  const [keepAlive, setKeepAlive] = useState("15m");
  const [contextWarning, setContextWarning] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => { void initialize(); }, []);

  async function initialize() {
    await Promise.all([loadModels(), loadConversations(), loadCapabilities()]);
  }

  async function loadCapabilities() {
    try {
      const response = await fetch(`${api}/api/capabilities`);
      const data = await response.json();
      if (response.ok) { setContextWindow(data.context_window); setKeepAlive(data.keep_alive); }
    } catch { /* Main connection status is shown above the chat. */ }
  }

  async function loadModels() {
    try {
      const response = await fetch(`${api}/api/models`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? "Could not load local models");
      setModels(data.models);
      setModel(current => data.models.some((item: Model) => item.name === current) ? current : data.models[0]?.name ?? "");
      setStatus(data.models.length ? "Local Ollama connected" : "Ollama connected — no models installed");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Backend unavailable");
    }
  }

  async function loadConversations() {
    try {
      const response = await fetch(`${api}/api/conversations`);
      const data = await response.json();
      if (response.ok) setConversations(data.conversations);
    } catch { /* Backend status is shown separately. */ }
  }

  async function openConversation(id: string) {
    if (sending) return;
    try {
      const response = await fetch(`${api}/api/conversations/${id}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? "Could not open saved conversation");
      setActiveId(id);
      setModel(data.model);
      setMessages(data.messages);
      setContextWarning("");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not open saved conversation");
    }
  }

  function newChat() {
    if (sending) return;
    setActiveId(null);
    setMessages([]);
    setPrompt("");
    setContextWarning("");
  }

  async function removeConversation(id: string, event: MouseEvent) {
    event.stopPropagation();
    if (sending) return;
    const conversation = conversations.find(item => item.id === id);
    if (!window.confirm(`Delete “${conversation?.title ?? "this chat"}”? This removes its saved messages.`)) return;
    const response = await fetch(`${api}/api/conversations/${id}`, { method: "DELETE" });
    if (!response.ok) { setStatus("Could not delete that conversation"); return; }
    if (activeId === id) newChat();
    await loadConversations();
  }

  async function send() {
    const content = prompt.trim();
    if (!content || !model || sending) return;
    const userMessage: Message = { role: "user", content };
    setMessages(current => [...current, userMessage, { role: "assistant", content: "", status: "streaming" }]);
    setPrompt("");
    setSending(true);
    setContextWarning("");
    const controller = new AbortController();
    abortRef.current = controller;
    let acceptedByServer = false;
    try {
      const response = await fetch(`${api}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model, content, conversation_id: activeId }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail ?? `Request failed (HTTP ${response.status})`);
      }
      const generatedId = response.headers.get("X-Conversation-Id");
      if (generatedId) setActiveId(generatedId);
      acceptedByServer = true;
      if (response.headers.get("X-Context-Truncated") === "true") {
        const estimate = response.headers.get("X-Context-Estimated-Tokens");
        setContextWarning(`This chat is longer than the ${contextWindow.toLocaleString()} token context. Older turns were left out of this reply${estimate ? ` (about ${estimate} estimated input tokens used)` : ""}.`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let completed = false;
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        buffer += decoder.decode(part.value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const event of events) {
          const raw = event.split("\n")
            .filter(line => line.startsWith("data:"))
            .map(line => line.slice(5).replace(/^ /, ""))
            .join("\n");
          if (!raw) continue;
          if (raw === "[DONE]") { completed = true; continue; }
          let data: { conversation_id?: string; error?: string; token?: string };
          try { data = JSON.parse(raw); } catch { continue; }
          if (data.conversation_id) setActiveId(data.conversation_id);
          if (data.error) throw new Error(data.error);
          if (data.token) setMessages(current => {
            const next = [...current];
            const last = next[next.length - 1];
            next[next.length - 1] = { ...last, content: last.content + data.token };
            return next;
          });
        }
      }
      setMessages(current => updateLastStatus(
        current,
        completed ? "complete" : "interrupted",
        completed ? undefined : "The response stream ended before completion. The saved partial reply is available.",
      ));
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        if (!acceptedByServer) {
          setMessages(current => current.slice(0, -2));
          setPrompt(content);
        } else {
          setMessages(current => updateLastStatus(current, "interrupted", "Stopped. The partial answer has been saved."));
        }
      } else {
        const message = error instanceof Error ? error.message : "The request failed";
        if (!acceptedByServer) {
          setMessages(current => current.slice(0, -2));
          setPrompt(content);
          setStatus(message);
        } else {
          setMessages(current => updateLastStatus(current, "error", message));
        }
      }
    } finally {
      abortRef.current = null;
      setSending(false);
      await loadConversations();
    }
  }

  function stop() { abortRef.current?.abort(); }

  return <main>
    <aside>
      <div className="brand">TAB<span>ZZAT</span></div>
      <p className="tagline">Tabish private server</p>
      <div className={`status ${status.includes("connected") ? "online" : "offline"}`}><i />{status}</div>
      <button className="new" onClick={newChat} disabled={sending}>＋ New chat</button>
      <nav><b>CONVERSATIONS</b>{conversations.length ? conversations.map(conversation =>
        <button className={`conversation ${conversation.id === activeId ? "active" : ""}`} onClick={() => void openConversation(conversation.id)} key={conversation.id} disabled={sending}>
          <span>{conversation.title}</span><em onClick={event => void removeConversation(conversation.id, event)} title="Delete conversation">×</em>
        </button>) : <p className="muted">Your saved chats appear here.</p>}</nav>
      <small>Private local inference<br />Model stays ready for {keepAlive}</small>
    </aside>
    <section>
      <header><div><h1>Tabzzat Tabish Server</h1><p>{contextWindow.toLocaleString()} token context · local model</p></div>
        <select value={model} onChange={event => setModel(event.target.value)} disabled={!models.length || sending} aria-label="Select local model">
          {models.length ? models.map(item => <option key={item.name}>{item.name}</option>) : <option>No local models</option>}
        </select>
      </header>
      <div className="messages">
        {contextWarning && <div className="context-warning">{contextWarning}</div>}
        {messages.length === 0 ? <div className="empty"><b>Start a local conversation.</b><span>Choose an installed model and ask anything.</span><div className="pills">
          <button onClick={() => setPrompt("Help me plan my day")}>Plan my day</button><button onClick={() => setPrompt("Explain this code")}>Explain code</button><button onClick={() => setPrompt("Teach me a topic step by step")}>Teach me</button>
        </div></div> : messages.map((message, index) => <article className={message.role} key={message.id ?? index}>
          <label>{message.role === "user" ? "YOU" : "LOCALMIND"}{message.status && message.status !== "complete" && <span className={`message-state ${message.status}`}>{message.status === "streaming" ? "Generating" : message.status}</span>}</label>
          {message.role === "assistant" ? message.content ? <Markdown text={message.content} /> : <p>{message.status === "streaming" ? "Thinking…" : message.error_message ?? "No text was generated."}</p> : <p>{message.content}</p>}
          {message.role === "assistant" && message.error_message && message.content && <div className="message-error">{message.error_message}</div>}
        </article>)}
      </div>
      <form onSubmit={event => { event.preventDefault(); void send(); }}>
        <textarea value={prompt} onChange={event => setPrompt(event.target.value)} placeholder="Ask your local model…" rows={3} disabled={!model || sending} />
        {sending ? <button className="stop" type="button" onClick={stop}>Stop ■</button> : <button type="submit" disabled={!model || !prompt.trim()}>Send ↗</button>}
      </form>
    </section>
  </main>;
}

function updateLastStatus(messages: Message[], status: MessageStatus, error_message?: string): Message[] {
  if (!messages.length) return messages;
  const next = [...messages];
  next[next.length - 1] = { ...next[next.length - 1], status, error_message };
  return next;
}

createRoot(document.getElementById("root")!).render(<App />);
