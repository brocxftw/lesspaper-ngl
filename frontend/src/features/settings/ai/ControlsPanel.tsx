import { useEffect, useMemo, useState } from "react";
import { useAIPolicy, useUpdateAIPolicy } from "@/lib/api/hooks";
import type { AIPolicyUpdate, AIProfile, PrivacyMode } from "@/lib/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import {
  SettingsCard,
  SettingsDisclosure,
  SettingsInfoBanner,
  SettingsSection,
} from "@/features/settings/components";
import { AiProfileOption } from "./AiProfileOption";
import { AiToggleRow } from "./AiToggleRow";
import { VisionAssignmentPanel } from "./VisionAssignmentPanel";
import { PRIVACY_MODE_COPY, PROFILE_OPTIONS } from "./workloadCopy";

function effectivePrivacyMode(
  privacyMode: PrivacyMode,
  blockRemote: boolean,
): PrivacyMode {
  if (privacyMode === "standard" && blockRemote) return "local_only";
  return privacyMode;
}

export function ControlsPanel() {
  const { data: policy, isLoading } = useAIPolicy();
  const updatePolicy = useUpdateAIPolicy();

  const [privacyMode, setPrivacyMode] = useState<PrivacyMode>("private_hybrid");
  const [remote, setRemote] = useState({
    allow_remote_qa: false,
    allow_remote_embeddings: false,
    allow_remote_vision: false,
    warn_before_remote: true,
  });
  const [automation, setAutomation] = useState({
    auto_tagging: false,
    auto_enrichment: false,
  });
  const [profile, setProfile] = useState<AIProfile>("balanced");
  const [limits, setLimits] = useState({
    retrieved_chunks: 8,
    max_context_tokens: 16000,
    max_output_tokens: 3072,
    conversation_history_tokens: 4000,
    parallel_llm_calls: 2,
  });
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!policy) return;
    const effective = effectivePrivacyMode(
      policy.privacy_mode as PrivacyMode,
      policy.block_remote_ai,
    );
    setPrivacyMode(effective);
    setRemote({
      allow_remote_qa: policy.allow_remote_qa,
      allow_remote_embeddings: policy.allow_remote_embeddings,
      allow_remote_vision: policy.allow_remote_vision,
      warn_before_remote: policy.warn_before_remote,
    });
    setAutomation({
      auto_tagging: policy.auto_tagging,
      auto_enrichment: policy.auto_enrichment,
    });
    setProfile(policy.profile);
    setLimits({
      retrieved_chunks: policy.retrieved_chunks,
      max_context_tokens: policy.max_context_tokens,
      max_output_tokens: policy.max_output_tokens,
      conversation_history_tokens: policy.conversation_history_tokens,
      parallel_llm_calls: policy.parallel_llm_calls,
    });
  }, [policy]);

  const remoteLocked = privacyMode === "local_only";

  const privacyHelper = PRIVACY_MODE_COPY[privacyMode]?.helper ?? "";

  const savePayload = useMemo((): AIPolicyUpdate => {
    const base: AIPolicyUpdate = {
      privacy_mode: privacyMode,
      block_remote_ai: false,
      allow_remote_qa: remoteLocked ? false : remote.allow_remote_qa,
      allow_remote_embeddings: remoteLocked ? false : remote.allow_remote_embeddings,
      allow_remote_vision: remoteLocked ? false : remote.allow_remote_vision,
      warn_before_remote: remote.warn_before_remote,
      auto_tagging: automation.auto_tagging,
      auto_enrichment: automation.auto_enrichment,
      profile,
      ...(profile === "custom" ? limits : {}),
    };
    return base;
  }, [automation, limits, privacyMode, profile, remote, remoteLocked]);

  const save = async () => {
    setSaveError(null);
    try {
      await updatePolicy.mutateAsync(savePayload);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save changes");
    }
  };

  if (isLoading || !policy) {
    return <p className="text-sm text-text-muted">Loading controls…</p>;
  }

  return (
    <div id="ai-policy" className="scroll-mt-4 space-y-6">
      <SettingsSection title="Privacy" description="Decide when lesspaper-ngl may use remote AI.">
        <SettingsCard>
          <div className="space-y-4">
            <div className="max-w-sm">
              <label className="text-xs font-medium text-text-muted">Privacy mode</label>
              <Select
                value={privacyMode}
                onValueChange={(value) => setPrivacyMode(value as PrivacyMode)}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="local_only">{PRIVACY_MODE_COPY.local_only.label}</SelectItem>
                  <SelectItem value="private_hybrid">
                    {PRIVACY_MODE_COPY.private_hybrid.label}
                  </SelectItem>
                  <SelectItem value="standard">{PRIVACY_MODE_COPY.standard.label}</SelectItem>
                </SelectContent>
              </Select>
              <p className="mt-1.5 text-xs text-text-secondary">{privacyHelper}</p>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-text-muted">
                Remote AI
              </p>
              <AiToggleRow
                label="Ask lesspaper-ngl"
                checked={remote.allow_remote_qa}
                disabled={remoteLocked}
                onCheckedChange={(checked) =>
                  setRemote({ ...remote, allow_remote_qa: checked })
                }
              />
              <AiToggleRow
                label="Embeddings"
                checked={remote.allow_remote_embeddings}
                disabled={remoteLocked}
                onCheckedChange={(checked) =>
                  setRemote({ ...remote, allow_remote_embeddings: checked })
                }
              />
              <AiToggleRow
                label="Vision"
                checked={remote.allow_remote_vision}
                disabled={remoteLocked}
                onCheckedChange={(checked) =>
                  setRemote({ ...remote, allow_remote_vision: checked })
                }
              />
            </div>

            <AiToggleRow
              label="Warn before sending documents remotely"
              checked={remote.warn_before_remote}
              onCheckedChange={(checked) =>
                setRemote({ ...remote, warn_before_remote: checked })
              }
            />

            <SettingsInfoBanner tone="muted">{policy.enforcement_note}</SettingsInfoBanner>
          </div>
        </SettingsCard>
      </SettingsSection>

      <SettingsSection title="Automation" description="Optional AI behaviour during document ingestion.">
        <SettingsCard>
          <div className="space-y-2">
            <AiToggleRow
              label="AI filing suggestions"
              description="Generate title, folder, tag, type and correspondent suggestions."
              checked={automation.auto_tagging}
              onCheckedChange={(checked) =>
                setAutomation({ ...automation, auto_tagging: checked })
              }
            />
            <AiToggleRow
              label="AI enrichment"
              description="Generate optional document summaries."
              checked={automation.auto_enrichment}
              onCheckedChange={(checked) =>
                setAutomation({ ...automation, auto_enrichment: checked })
              }
            />
          </div>
        </SettingsCard>
      </SettingsSection>

      <SettingsSection
        title="Response profile"
        description="Controls Ask lesspaper-ngl retrieval depth and output limits, not which model is used."
      >
        <SettingsCard>
          <div className="space-y-2">
            {PROFILE_OPTIONS.map((option) => (
              <AiProfileOption
                key={option.id}
                label={option.label}
                tagline={option.tagline}
                spec={option.spec}
                selected={profile === option.id}
                onSelect={() => setProfile(option.id)}
              />
            ))}
          </div>

          {profile === "custom" && (
            <SettingsDisclosure title="Custom limits" defaultOpen className="mt-4">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                {Object.entries(limits).map(([key, value]) => (
                  <label key={key} className="text-xs text-text-muted">
                    {key.replaceAll("_", " ")}
                    <Input
                      type="number"
                      min={1}
                      className="mt-1"
                      value={value}
                      onChange={(event) =>
                        setLimits({ ...limits, [key]: Number(event.target.value) })
                      }
                    />
                  </label>
                ))}
              </div>
            </SettingsDisclosure>
          )}
        </SettingsCard>
      </SettingsSection>

      <SettingsDisclosure title="Advanced: experimental vision">
        <VisionAssignmentPanel />
      </SettingsDisclosure>

      <div className="flex flex-wrap items-center justify-end gap-3">
        {saveError && (
          <p role="alert" className="text-sm text-danger">
            {saveError}
          </p>
        )}
        <Button onClick={() => void save()} disabled={updatePolicy.isPending}>
          {updatePolicy.isPending ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </div>
  );
}
