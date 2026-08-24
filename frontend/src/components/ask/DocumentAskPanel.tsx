import { useEffect, useRef, useState } from "react";
import {
  Eraser,
  Leaf,
  Loader2,
  Plus,
  Send,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import { ApiError } from "@/lib/api/client";
import {
  useAIHealth,
  useAskConversation,
  useAskDocument,
  useClearAskConversation,
  useNewAskConversation,
} from "@/lib/api/hooks";
import type {
  AskMessage,
  Citation,
} from "@/lib/api/types";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { AnswerBody, SourcesDrawer } from "./MarkdownResponse";
import { cn } from "@/lib/utils";

const SUGGESTED_PROMPTS = [
  "Summarise the main argument",
  "What are the key ideas?",
  "What evidence supports the author's conclusion?",
];

export interface DocumentAskPanelProps {
  documentId: string;
  documentTitle?: string;
  active?: boolean;
  onClose?: () => void;
  onCitationActivate: (citation: Citation) => void;
  className?: string;
}

type PendingStatus = "retrieving" | "generating" | null;

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

/** Stable thread order: time, then user before assistant on ties. */
function sortMessages(messages: AskMessage[]): AskMessage[] {
  return [...messages].sort((a, b) => {
    const ta = new Date(a.created_at).getTime();
    const tb = new Date(b.created_at).getTime();
    if (ta !== tb) return ta - tb;
    if (a.role !== b.role) return a.role === "user" ? -1 : 1;
    return a.id.localeCompare(b.id);
  });
}

export function DocumentAskPanel({
  documentId,
  active = true,
  onClose,
  onCitationActivate,
  className,
}: DocumentAskPanelProps) {
  const [draft, setDraft] = useState("");
  const [localMessages, setLocalMessages] = useState<AskMessage[] | null>(null);
  const [pendingStatus, setPendingStatus] = useState<PendingStatus>(null);
  const [queue, setQueue] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingRemote, setPendingRemote] = useState(false);
  const [activeCitation, setActiveCitation] = useState<number | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [confirmNew, setConfirmNew] = useState(false);
  const [persistWarning, setPersistWarning] = useState<string | null>(null);
  const [composerFocused, setComposerFocused] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const abortRef = useRef<AbortController | null>(null);
  const queueRef = useRef<string[]>([]);
  const processingRef = useRef(false);
  const serverMessagesRef = useRef<AskMessage[]>([]);
  const skipDrainRef = useRef(false);

  const { data: conversation, isLoading, isError, refetch } =
    useAskConversation(active ? documentId : undefined);
  const ask = useAskDocument();
  const newChat = useNewAskConversation();
  const clearChat = useClearAskConversation();
  const { data: aiHealth } = useAIHealth();
  const chatAvailable = aiHealth?.chat.status === "available";

  const serverMessages = conversation?.messages ?? [];
  serverMessagesRef.current = serverMessages;
  const messages = sortMessages(localMessages ?? serverMessages);
  const isNewSession = messages.length === 0 && !pendingStatus && queue.length === 0;
  const composerPlaceholder = isNewSession
    ? "Ask something…"
    : "Ask follow up…";

  useEffect(() => {
    setLocalMessages(null);
    setError(null);
    setPendingRemote(false);
    setPersistWarning(null);
    setActiveCitation(null);
    setDraft("");
    setQueue([]);
    queueRef.current = [];
    skipDrainRef.current = true;
    abortRef.current?.abort();
    abortRef.current = null;
    processingRef.current = false;
    setPendingStatus(null);
  }, [documentId]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (localMessages == null) return;
    if (pendingStatus || queue.length > 0 || processingRef.current) return;
    // Once server catches up after invalidate, drop optimistic overlay.
    if (serverMessages.length >= localMessages.length) {
      setLocalMessages(null);
    }
  }, [serverMessages, localMessages, pendingStatus, queue.length]);

  useEffect(() => {
    if (!stickToBottom.current || !threadRef.current) return;
    threadRef.current.scrollTop = threadRef.current.scrollHeight;
  }, [messages, pendingStatus, queue]);

  const activateCitation = (citation: Citation) => {
    setActiveCitation(citation.display_number ?? null);
    onCitationActivate(citation);
  };

  const stopAsk = () => {
    // Stop only the in-flight turn; queued follow-ups remain and will start next.
    skipDrainRef.current = false;
    abortRef.current?.abort();
  };

  const isAbortError = (err: unknown) =>
    (err instanceof DOMException && err.name === "AbortError") ||
    (err instanceof Error && err.name === "AbortError");

  const runAskAndDrain = async (question: string, confirmRemote = false) => {
    if (processingRef.current) return;
    processingRef.current = true;
    setError(null);
    setPersistWarning(null);
    setPendingRemote(false);
    stickToBottom.current = true;

    const optimisticUser: AskMessage = {
      id: `temp-user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      role: "user",
      content: question,
      citations: [],
      created_at: new Date().toISOString(),
    };
    setLocalMessages((prev) =>
      sortMessages([...(prev ?? serverMessagesRef.current), optimisticUser]),
    );
    setPendingStatus("retrieving");

    const controller = new AbortController();
    abortRef.current = controller;
    let shouldDrain = true;
    let restoreDraft: string | null = null;

    try {
      setPendingStatus("generating");
      const result = await ask.mutateAsync({
        documentId,
        question,
        scope: "document",
        document_id: documentId,
        confirm_remote: confirmRemote,
        signal: controller.signal,
      });

      const assistantCreated = new Date(
        new Date(optimisticUser.created_at).getTime() + 1,
      ).toISOString();
      const assistant: AskMessage = {
        id: result.assistant_message_id ?? `temp-assistant-${Date.now()}`,
        role: "assistant",
        content: result.answer,
        citations: result.citations.map((c, i) => ({
          display_number: c.display_number ?? i + 1,
          chunk_id: c.chunk_id,
          document_id: c.document_id,
          page_number: c.page_number,
          title: c.title,
          quote: c.quote,
        })),
        created_at: assistantCreated,
      };
      setLocalMessages((prev) => {
        const base = prev ?? serverMessagesRef.current;
        const withoutTemp = base.filter((m) => m.id !== optimisticUser.id);
        const userMsg: AskMessage = {
          ...optimisticUser,
          id: result.user_message_id ?? optimisticUser.id,
        };
        return sortMessages([...withoutTemp, userMsg, assistant]);
      });
      if (result.persist_failed) {
        setPersistWarning(
          "Your answer was generated, but the conversation could not be saved.",
        );
      }
    } catch (err) {
      if (isAbortError(err)) {
        setLocalMessages((prev) => {
          const base = (prev ?? serverMessagesRef.current).filter(
            (m) => m.id !== optimisticUser.id,
          );
          return base.length ? sortMessages(base) : null;
        });
        restoreDraft = question;
        // Still drain queue after stop so follow-ups proceed.
      } else {
        shouldDrain = false;
        setLocalMessages((prev) => {
          const base = (prev ?? serverMessagesRef.current).filter(
            (m) => m.id !== optimisticUser.id,
          );
          return base.length ? sortMessages(base) : null;
        });
        setDraft(question);
        if (err instanceof ApiError && err.isForbidden) {
          setPendingRemote(true);
          setError(
            err.message ||
              "This provider is remote. Confirm to send the question outside your host.",
          );
        } else {
          setError(
            err instanceof Error
              ? err.message
              : "I couldn't complete that request.",
          );
        }
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
      setPendingStatus(null);
      processingRef.current = false;
      if (restoreDraft) {
        setDraft((d) => (d.trim() || queueRef.current.length ? d : restoreDraft!));
      }
    }

    if (shouldDrain && !skipDrainRef.current) {
      const [next, ...rest] = queueRef.current;
      if (next) {
        queueRef.current = rest;
        setQueue(rest);
        void runAskAndDrain(next, false);
      }
    } else if (skipDrainRef.current) {
      skipDrainRef.current = false;
    }
  };

  const submit = (confirmRemote = false, overrideQuestion?: string) => {
    const question = (overrideQuestion ?? draft).trim();
    if (!question) return;

    if (pendingStatus || processingRef.current) {
      queueRef.current = [...queueRef.current, question];
      setQueue(queueRef.current);
      setDraft("");
      stickToBottom.current = true;
      return;
    }

    setDraft("");
    void runAskAndDrain(question, confirmRemote);
  };

  const handleNewChat = async () => {
    setConfirmNew(false);
    skipDrainRef.current = true;
    abortRef.current?.abort();
    queueRef.current = [];
    setQueue([]);
    await newChat.mutateAsync(documentId);
    setLocalMessages([]);
    setError(null);
    setPersistWarning(null);
    setActiveCitation(null);
  };

  const handleClear = async () => {
    setConfirmClear(false);
    skipDrainRef.current = true;
    abortRef.current?.abort();
    queueRef.current = [];
    setQueue([]);
    await clearChat.mutateAsync(documentId);
    setLocalMessages([]);
    setError(null);
    setPersistWarning(null);
    setActiveCitation(null);
  };

  if (!chatAvailable) {
    return (
      <div className={cn("flex h-full flex-col p-4", className)}>
        <PanelHeader onClose={onClose} />
        <p className="mt-6 text-sm text-text-secondary">
          Ask lesspaper-ngl is currently unavailable. The document remains fully accessible.
        </p>
      </div>
    );
  }

  return (
    <div className={cn("flex h-full min-h-0 flex-col bg-surface", className)}>
      <PanelHeader
        onClose={onClose}
        onNew={() => {
          if (messages.length > 0 || queue.length > 0) setConfirmNew(true);
          else void handleNewChat();
        }}
        onClear={() => setConfirmClear(true)}
        clearDisabled={messages.length === 0 && queue.length === 0}
      />

      <div
        ref={threadRef}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3 scrollbar-thin"
        onScroll={(e) => {
          const el = e.currentTarget;
          stickToBottom.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
      >
        {isLoading && (
          <p className="text-sm text-text-muted" aria-live="polite">
            Loading conversation…
          </p>
        )}
        {isError && (
          <div className="rounded-xl border border-surface-border p-3 text-sm">
            <p className="text-text-primary">
              The previous conversation could not be loaded.
            </p>
            <p className="mt-1 text-text-secondary">
              You can still start a new conversation.
            </p>
            <div className="mt-2 flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => void refetch()}>
                Retry
              </Button>
              <Button size="sm" onClick={() => void handleNewChat()}>
                Start new chat
              </Button>
            </div>
          </div>
        )}

        {!isLoading && !isError && isNewSession && (
          <EmptyState onPick={(prompt) => submit(false, prompt)} />
        )}

        {messages.map((message) => (
          <MessageCard
            key={message.id}
            message={message}
            activeCitation={activeCitation}
            onActivate={activateCitation}
          />
        ))}

        {pendingStatus && (
          <div className="rounded-xl border border-surface-border bg-surface p-3.5">
            <div className="mb-2 flex items-center gap-2 text-xs text-text-muted">
              <Leaf className="h-3.5 w-3.5 text-accent" />
              lesspaper-ngl
            </div>
            <p className="flex items-center gap-2 text-sm text-text-secondary" aria-live="polite">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {pendingStatus === "retrieving"
                ? "Searching this document…"
                : "Generating answer…"}
            </p>
          </div>
        )}

        {queue.map((queued, index) => (
          <div
            key={`queued-${index}-${queued.slice(0, 24)}`}
            className="rounded-xl border border-dashed border-accent/30 bg-accent/[0.04] p-3.5"
          >
            <div className="mb-2 flex items-center justify-between gap-2 text-xs text-text-muted">
              <span className="font-medium text-text-secondary">You</span>
              <span>Queued</span>
            </div>
            <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-text-primary">
              {queued}
            </p>
          </div>
        ))}
      </div>

      {(error || persistWarning) && (
        <div className="space-y-2 border-t border-surface-border px-3 py-2">
          {error && (
            <div className="rounded-md bg-danger/10 px-3 py-2 text-xs text-danger">
              <p>{error}</p>
              {pendingRemote ? (
                <Button
                  size="sm"
                  className="mt-2"
                  onClick={() => submit(true)}
                >
                  Confirm remote AI and ask
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="secondary"
                  className="mt-2"
                  onClick={() => submit(false)}
                >
                  Retry
                </Button>
              )}
            </div>
          )}
          {persistWarning && (
            <p className="text-xs text-amber-700 dark:text-amber-400">{persistWarning}</p>
          )}
        </div>
      )}

      <div className="border-t border-surface-border p-3">
        <div className="relative">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={
              pendingStatus
                ? "Type a follow-up to queue…"
                : composerPlaceholder
            }
            rows={1}
            className="max-h-40 min-h-[44px] resize-none rounded-[10px] pr-12"
            onFocus={() => setComposerFocused(true)}
            onBlur={() => setComposerFocused(false)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(false);
              }
            }}
          />
          {pendingStatus ? (
            draft.trim() ? (
              <Button
                size="icon"
                className="absolute bottom-2 right-2 h-8 w-8 rounded-lg"
                aria-label="Queue follow-up"
                title="Queue follow-up"
                onClick={() => submit(false)}
              >
                <Send className="h-3.5 w-3.5" />
              </Button>
            ) : (
              <Button
                size="icon"
                variant="danger"
                className={cn(
                  "absolute bottom-2 right-2 h-8 w-8 rounded-lg transition-colors",
                  composerFocused
                    ? "bg-danger hover:bg-red-700"
                    : "bg-danger/35 hover:bg-danger/55",
                )}
                aria-label="Stop generating"
                title="Stop"
                onClick={stopAsk}
              >
                <Square className="h-3 w-3 fill-current" />
              </Button>
            )
          ) : (
            <Button
              size="icon"
              className="absolute bottom-2 right-2 h-8 w-8 rounded-lg"
              disabled={!draft.trim()}
              aria-label="Send"
              onClick={() => submit(false)}
            >
              <Send className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>

      <Dialog open={confirmClear} onOpenChange={setConfirmClear}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Clear this chat?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-text-secondary">
            This will permanently remove the current conversation for this document.
          </p>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmClear(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={clearChat.isPending}
              onClick={() => void handleClear()}
            >
              Clear chat
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmNew} onOpenChange={setConfirmNew}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Start a new chat?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-text-secondary">
            This replaces the current conversation for this document.
          </p>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmNew(false)}>
              Cancel
            </Button>
            <Button disabled={newChat.isPending} onClick={() => void handleNewChat()}>
              New chat
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PanelHeader({
  onClose,
  onNew,
  onClear,
  clearDisabled,
}: {
  onClose?: () => void;
  onNew?: () => void;
  onClear?: () => void;
  clearDisabled?: boolean;
}) {
  return (
    <div className="flex shrink-0 items-start justify-between gap-2 border-b border-surface-border px-3 py-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-accent" />
          <h2 className="text-sm font-semibold text-text-primary">Ask this document</h2>
        </div>
        <p className="mt-0.5 text-xs text-text-muted">Scope: This document</p>
      </div>
      <div className="flex shrink-0 items-center gap-0.5">
        {onNew && (
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            aria-label="New chat"
            title="Start a new conversation"
            onClick={onNew}
          >
            <Plus className="h-4 w-4" />
          </Button>
        )}
        {onClear && (
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            aria-label="Clear chat"
            title="Delete this conversation"
            disabled={clearDisabled}
            onClick={onClear}
          >
            <Eraser className="h-4 w-4" />
          </Button>
        )}
        {onClose && (
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            aria-label="Close Ask lesspaper-ngl"
            title="Close Ask lesspaper-ngl"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="rounded-xl border border-dashed border-surface-border p-4">
      <h3 className="text-sm font-medium text-text-primary">Ask about this document</h3>
      <p className="mt-1 text-xs text-text-secondary">
        Ask questions about concepts, details, or evidence contained in the open document.
      </p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {SUGGESTED_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onPick(prompt)}
            className="rounded-full border border-surface-border px-2.5 py-1 text-[11px] text-text-secondary hover:border-accent/40 hover:text-accent"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

function MessageCard({
  message,
  activeCitation,
  onActivate,
}: {
  message: AskMessage;
  activeCitation: number | null;
  onActivate: (citation: Citation) => void;
}) {
  const isUser = message.role === "user";
  return (
    <div
      className={cn(
        "rounded-xl border p-3.5",
        isUser
          ? "border-accent/20 bg-accent/[0.06]"
          : "border-surface-border bg-surface",
      )}
    >
      <div className="mb-2 flex items-center justify-between gap-2 text-xs text-text-muted">
        <span className="flex items-center gap-1.5 font-medium text-text-secondary">
          {isUser ? (
            "You"
          ) : (
            <>
              <Leaf className="h-3.5 w-3.5 text-accent" />
              lesspaper-ngl
            </>
          )}
        </span>
        <span>{formatTime(message.created_at)}</span>
      </div>
      {isUser ? (
        <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-text-primary">
          {message.content}
        </p>
      ) : (
        <>
          <AnswerBody
            content={message.content}
            citations={message.citations}
            activeNumber={activeCitation}
            onActivate={onActivate}
          />
          <SourcesDrawer
            citations={message.citations}
            activeNumber={activeCitation}
            onOpen={onActivate}
          />
        </>
      )}
    </div>
  );
}
