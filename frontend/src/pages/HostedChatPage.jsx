import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router";
import { MAX_MESSAGE_LENGTH, getChatProfile, sendChatMessage } from "../api/publicChat.js";
import ErrorBanner from "../components/ErrorBanner.jsx";
import Spinner from "../components/Spinner.jsx";
import styles from "./HostedChatPage.module.css";


const LINK_PROBLEMS = {
  404: {
    title: "This chat link doesn't exist",
    text: "The link may be mistyped, or the business may have replaced it with a new one.",
  },
  403: {
    title: "This chat is currently unavailable",
    text: "The business has turned this chat off. Please try again later or contact them another way.",
  },
};

export default function HostedChatPage() {
  const { publicId } = useParams();

  const [profile, setProfile] = useState(null);
  const [profileError, setProfileError] = useState(null); // ApiError
  const [loadAttempt, setLoadAttempt] = useState(0);

  // 2. The conversation. The token is kept in memory only: a reload starts a new chat.
  const [messages, setMessages] = useState([]); // [{role: "user" | "assistant", text}]
  const [conversationToken, setConversationToken] = useState(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState(null);
  const [closedProblem, setClosedProblem] = useState(null); // link went 403/404 mid-chat
  const [waitUntil, setWaitUntil] = useState(null); // ms timestamp after a 429
  const [now, setNow] = useState(Date.now());

  const bottomRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setProfile(null);
    setProfileError(null);
    getChatProfile(publicId)
      .then((found) => {
        if (!cancelled) setProfile(found);
      })
      .catch((error) => {
        if (!cancelled) setProfileError(error);
      });
    return () => {
      cancelled = true;
    };
  }, [publicId, loadAttempt]);

  // Keep the newest message in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, sending]);

  // While rate limited, tick once a second so the countdown updates.
  useEffect(() => {
    if (!waitUntil) return;
    const timer = setInterval(() => {
      setNow(Date.now());
      if (Date.now() >= waitUntil) setWaitUntil(null);
    }, 1000);
    return () => clearInterval(timer);
  }, [waitUntil]);

  async function handleSend(event) {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || sending || waitUntil || closedProblem) return;

    setMessages((current) => [...current, { role: "user", text }]);
    setDraft("");
    setSending(true);
    setSendError(null);
    try {
      const result = await sendChatMessage(publicId, text, conversationToken);
      setConversationToken(result.conversation_token);
      setMessages((current) => [...current, { role: "assistant", text: result.reply }]);
    } catch (error) {
      // The message was not answered: take it back out and return it to the
      // input box so the visitor can send it again.
      setMessages((current) => current.slice(0, -1));
      setDraft(text);
      if (error.status === 403 || error.status === 404) {
        setClosedProblem(LINK_PROBLEMS[error.status]);
      } else if (error.status === 429 && error.retryAfter) {
        setNow(Date.now());
        setWaitUntil(Date.now() + error.retryAfter * 1000);
        setSendError("Too many messages right now.");
      } else {
        setSendError(error.message);
      }
    } finally {
      setSending(false);
    }
  }

  // Enter sends, Shift+Enter makes a new line.
  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) handleSend(event);
  }

  if (profileError) {
    const problem = LINK_PROBLEMS[profileError.status];
    return (
      <main className="page-center">
        <div className={`card ${styles.problem}`}>
          {problem ? (
            <>
              <h1>{problem.title}</h1>
              <p className="muted">{problem.text}</p>
            </>
          ) : (
            <ErrorBanner message={profileError.message} onRetry={() => setLoadAttempt((n) => n + 1)} />
          )}
        </div>
      </main>
    );
  }

  if (!profile) {
    return (
      <main className="page-center">
        <Spinner label="Opening chat…" />
      </main>
    );
  }

  const secondsLeft = waitUntil ? Math.max(1, Math.ceil((waitUntil - now) / 1000)) : 0;
  const canSend = draft.trim() !== "" && !sending && !waitUntil && !closedProblem;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1>{profile.business_name}</h1>
        <p>{profile.name}</p>
      </header>

      <div className={styles.messages}>
        {/* The greeting is shown only on screen; it is not sent to the agent. */}
        <div className={styles.assistant}>
          {profile.greeting || `Hi! How can ${profile.business_name} help you today?`}
        </div>
        {messages.map((message, index) => (
          <div key={index} className={message.role === "user" ? styles.user : styles.assistant}>
            {message.text}
          </div>
        ))}
        {sending && <div className={`${styles.assistant} ${styles.typing}`}>Typing…</div>}
        <div ref={bottomRef} />
      </div>

      <footer className={styles.footer}>
        {closedProblem ? (
          <div className={styles.closed}>
            <strong>{closedProblem.title}</strong>
            <span className="muted">{closedProblem.text}</span>
          </div>
        ) : (
          <>
            <ErrorBanner
              message={sendError && (waitUntil ? `${sendError} You can send again in ${secondsLeft}s.` : sendError)}
            />
            <form className={styles.composer} onSubmit={handleSend}>
              <textarea
                rows={2}
                maxLength={MAX_MESSAGE_LENGTH}
                placeholder="Type your message…"
                aria-label="Message"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={handleKeyDown}
              />
              <button type="submit" disabled={!canSend}>
                {sending ? "Sending…" : "Send"}
              </button>
            </form>
          </>
        )}
        <p className={styles.powered}>Powered by Warmline</p>
      </footer>
    </main>
  );
}
