import { useState } from "react";
import { Link } from "react-router-dom";
import { useAbout, useSession } from "@/lib/api/hooks";
import { Button } from "@/components/ui/Button";
import lesspaperNglLogo from "@/assets/brand/lesspaper-ngl_logo.svg";
import {
  SettingsCard,
  SettingsContent,
  SettingsEmptyState,
  SettingsPageHeader,
  SettingsSection,
} from "@/features/settings/components";

export function AboutPage() {
  const { data, isLoading, error } = useAbout();
  const { data: session } = useSession();
  const [copied, setCopied] = useState(false);

  const copyRevision = async (value: string) => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
  };

  return (
    <SettingsContent>
      <SettingsPageHeader
        title="About"
        description="What version this is, and how lesspaper-ngl handles your data."
      />
      {isLoading ? (
        <SettingsEmptyState>Loading product information…</SettingsEmptyState>
      ) : error || !data ? (
        <p role="alert" className="text-danger">Product metadata is unavailable.</p>
      ) : (
        <SettingsSection title="lesspaper-ngl">
          <SettingsCard>
            <div className="flex flex-wrap items-start gap-4">
              <img src={lesspaperNglLogo} alt="lesspaper-ngl" width={48} height={48} className="h-12 w-12" />
              <div className="min-w-0 flex-1">
                <p className="text-base font-semibold text-text-primary">{data.product}</p>
                <p className="mt-1 text-sm text-text-secondary">{data.description}</p>
                <p className="mt-3 text-sm">
                  <span className="text-text-muted">Version </span>
                  <span className="font-mono font-medium text-text-primary">{data.version}</span>
                </p>
                {(data.build_revision || data.build_date) && (
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-text-muted">
                    {data.build_revision && (
                      <>
                        <span className="font-mono">{data.build_revision}</span>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => void copyRevision(data.build_revision!)}
                        >
                          {copied ? "Copied" : "Copy revision"}
                        </Button>
                      </>
                    )}
                    {data.build_date && <span>{data.build_date}</span>}
                  </div>
                )}
              </div>
            </div>
          </SettingsCard>
        </SettingsSection>
      )}

      <SettingsSection title="Privacy & data handling">
        <SettingsCard>
          <div className="space-y-3 text-sm leading-6 text-text-secondary">
            <p>lesspaper-ngl stores your documents, text, metadata and search indexes on the system you or your administrator control. It is local-first by design.</p>
            <p>AI is optional. If a remote AI provider is enabled, lesspaper-ngl may send document content according to the configured privacy policy.</p>
            <p>Provider credentials are encrypted and never shown in full. Logs are redacted so prompts, document text, cookies and tokens are not kept.</p>
          </div>
          {session?.user.is_admin ? (
            <Link
              className="mt-4 inline-flex text-sm font-medium text-accent hover:underline"
              to="/settings/artificial-intelligence?tab=controls#ai-policy"
            >
              Review AI Policy →
            </Link>
          ) : (
            <p className="mt-4 text-sm text-text-muted">AI Policy is managed by your lesspaper-ngl administrator.</p>
          )}
        </SettingsCard>
      </SettingsSection>

      {data && Object.keys(data.project_links).length > 0 && (
        <SettingsSection title="Project links">
          <div className="flex flex-wrap gap-2">
            {Object.entries(data.project_links).map(([label, url]) => (
              <a
                key={label}
                href={url}
                target="_blank"
                rel="noreferrer"
                className="rounded-md border border-surface-border bg-surface px-3 py-1.5 text-sm capitalize text-text-primary hover:bg-surface-hover"
              >
                {label}
              </a>
            ))}
          </div>
        </SettingsSection>
      )}
    </SettingsContent>
  );
}
