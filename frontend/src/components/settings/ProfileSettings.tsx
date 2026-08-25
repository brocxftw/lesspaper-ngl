import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  ChevronRight,
  Gauge,
  KeyRound,
  Lock,
  Mail,
  Monitor,
  Pencil,
  RotateCcw,
  Users,
} from "lucide-react";
import {
  useChangePassword,
  useDeleteAvatar,
  useMyUsage,
  useMySessions,
  useRevokeSession,
  useSignOutOtherSessions,
  useSession,
  useUpdateProfile,
  useUploadAvatar,
  useApiTokens,
  useCreateApiToken,
  useRevokeApiToken,
} from "@/lib/api/hooks";
import { api } from "@/lib/api/client";
import { formatBytes, getInitials } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import {
  SettingsCard,
  SettingsContent,
  SettingsInfoBanner,
  SettingsPageHeader,
  SettingsRow,
  SettingsSection,
  SettingsStatusBadge,
} from "@/features/settings/components";

export function ProfileSettings() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data: session } = useSession();
  const { data: usage } = useMyUsage();
  const { data: sessions = [], isLoading: sessionsLoading } = useMySessions();
  const revokeSession = useRevokeSession();
  const signOutOthers = useSignOutOtherSessions();
  const updateProfile = useUpdateProfile();
  const changePassword = useChangePassword();
  const uploadAvatar = useUploadAvatar();
  const deleteAvatar = useDeleteAvatar();
  const { data: apiTokens = [], isLoading: tokensLoading } = useApiTokens();
  const createApiToken = useCreateApiToken();
  const revokeApiToken = useRevokeApiToken();
  const fileRef = useRef<HTMLInputElement>(null);

  const [editing, setEditing] = useState(false);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [profileMsg, setProfileMsg] = useState<string | null>(null);
  const [passwordMsg, setPasswordMsg] = useState<string | null>(null);
  const [avatarBust, setAvatarBust] = useState(() => Date.now());
  const [tokenName, setTokenName] = useState("");
  const [newTokenSecret, setNewTokenSecret] = useState<string | null>(null);
  const [tokenMsg, setTokenMsg] = useState<string | null>(null);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [tokensOpen, setTokensOpen] = useState(false);

  useEffect(() => {
    if (session?.user) {
      setUsername(session.user.username);
      setDisplayName(session.user.display_name);
    }
  }, [session?.user]);

  const saveProfile = async () => {
    setProfileMsg(null);
    try {
      await updateProfile.mutateAsync({
        username: username.trim(),
        display_name: displayName.trim(),
      });
      setProfileMsg("Profile updated");
      setEditing(false);
    } catch (err) {
      setProfileMsg(err instanceof Error ? err.message : "Update failed");
    }
  };

  const savePassword = async () => {
    setPasswordMsg(null);
    if (newPassword !== confirmPassword) {
      setPasswordMsg("New passwords do not match");
      return;
    }
    if (newPassword.length < 8) {
      setPasswordMsg("New password must be at least 8 characters");
      return;
    }
    try {
      await changePassword.mutateAsync({
        current_password: currentPassword,
        new_password: newPassword,
      });
      navigate("/login", {
        replace: true,
        state: { notice: "Password updated. Sign in with your new password." },
      });
    } catch (err) {
      setPasswordMsg(err instanceof Error ? err.message : "Password change failed");
    }
  };

  const onAvatarSelected = async (file: File | undefined) => {
    if (!file) return;
    setProfileMsg(null);
    try {
      await uploadAvatar.mutateAsync(file);
      setAvatarBust(Date.now());
      setProfileMsg("Profile picture updated");
    } catch (err) {
      setProfileMsg(err instanceof Error ? err.message : "Avatar upload failed");
    }
  };

  const removeAvatar = async () => {
    setProfileMsg(null);
    try {
      await deleteAvatar.mutateAsync();
      setAvatarBust(Date.now());
      setProfileMsg("Profile picture removed");
    } catch (err) {
      setProfileMsg(err instanceof Error ? err.message : "Could not remove avatar");
    }
  };

  const user = session?.user;
  const hasAvatar = !!user?.has_avatar;
  const tokenCount = apiTokens.length;
  const sessionCount = sessions.length;

  return (
    <SettingsContent>
      <SettingsPageHeader
        title="Profile"
        description={<><span className="md:hidden">Manage your account and security.</span><span className="hidden md:inline">Manage your account, security, sessions and API access.</span></>}
        actions={
          <Button type="button" variant="outline" size="sm" onClick={() => setEditing(true)} disabled={editing}>
            <Pencil className="h-3.5 w-3.5" strokeWidth={1.75} />
            Edit profile
          </Button>
        }
      />
      {(location.state as { notice?: string } | null)?.notice && (
        <p role="status" className="rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
          {(location.state as { notice?: string }).notice}
        </p>
      )}

      <SettingsSection index={1} title="Account" description="Your identity in lesspaper-ngl.">
        <SettingsCard>
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex items-center gap-4">
              <button
                type="button"
                className="relative flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-full bg-surface-muted text-lg font-medium text-text-primary ring-offset-2 hover:ring-2 hover:ring-accent"
                onClick={() => fileRef.current?.click()}
                title="Change profile picture"
              >
                {hasAvatar ? (
                  <img src={api.avatarUrl(avatarBust)} alt="" className="h-full w-full object-cover" />
                ) : (
                  getInitials(user?.display_name || user?.username || "?")
                )}
              </button>
              <div className="min-w-0 space-y-1.5">
                <p className="truncate text-base font-semibold text-text-primary">
                  {user?.display_name || user?.username}
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <SettingsStatusBadge tone={user?.is_admin ? "info" : "neutral"}>
                    {user?.is_admin ? "Administrator" : "User"}
                  </SettingsStatusBadge>
                  <span className="text-xs text-text-muted">
                    {user?.is_admin ? "Full access to lesspaper-ngl administration." : "Standard account access."}
                  </span>
                </div>
                {usage && (
                  <p className="hidden text-xs text-text-muted md:block">
                    Storage {formatBytes(usage.storage_used_bytes)}
                    {usage.storage_quota_bytes != null
                      ? ` / ${formatBytes(usage.storage_quota_bytes)}`
                      : " · unlimited"}
                    {" · "}
                    AI {usage.ai_requests_this_month}
                    {usage.ai_monthly_request_quota != null
                      ? ` / ${usage.ai_monthly_request_quota} this month`
                      : " requests this month · unlimited"}
                  </p>
                )}
                <div className="flex flex-wrap gap-2 pt-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => fileRef.current?.click()}
                    disabled={uploadAvatar.isPending}
                  >
                    Change picture
                  </Button>
                  {hasAvatar && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => void removeAvatar()}
                      disabled={deleteAvatar.isPending}
                    >
                      Use initials
                    </Button>
                  )}
                </div>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  onChange={(e) => void onAvatarSelected(e.target.files?.[0])}
                />
              </div>
            </div>
            <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-2 lg:max-w-md">
              <div>
                <label className="text-xs text-text-secondary" htmlFor="profile-username">
                  Username
                </label>
                <Input
                  id="profile-username"
                  className="mt-1"
                  autoComplete="username"
                  value={username}
                  disabled={!editing}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs text-text-secondary" htmlFor="profile-display-name">
                  Display name
                </label>
                <Input
                  id="profile-display-name"
                  className="mt-1"
                  autoComplete="name"
                  value={displayName}
                  disabled={!editing}
                  onChange={(e) => setDisplayName(e.target.value)}
                />
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="self-start md:hidden"
              onClick={() => setEditing(true)}
              disabled={editing}
            >
              <Pencil className="h-3.5 w-3.5" strokeWidth={1.75} />
              Edit account
            </Button>
          </div>
          {profileMsg && <p className="mt-4 text-xs text-text-secondary">{profileMsg}</p>}
          {editing && (
            <div className="mt-5 flex justify-end">
              <Button type="button" size="sm" onClick={() => void saveProfile()} disabled={updateProfile.isPending}>
                Save changes
              </Button>
            </div>
          )}
        </SettingsCard>
      </SettingsSection>

      <SettingsSection title="Usage" description="Your current storage and AI request allowance." className="md:hidden">
        <div className="grid gap-3 min-[380px]:grid-cols-2">
          <SettingsCard padding="sm">
            <p className="text-xs font-medium text-text-secondary">Storage</p>
            <p className="mt-1 text-lg font-semibold text-text-primary">
              {usage ? formatBytes(usage.storage_used_bytes) : "—"}
            </p>
            <p className="mt-0.5 text-xs text-text-muted">
              {usage?.storage_quota_bytes != null ? `${formatBytes(usage.storage_quota_bytes)} limit` : "Unlimited"}
            </p>
          </SettingsCard>
          <SettingsCard padding="sm">
            <p className="text-xs font-medium text-text-secondary">AI requests</p>
            <p className="mt-1 text-lg font-semibold text-text-primary">
              {usage ? usage.ai_requests_this_month.toLocaleString() : "—"}
            </p>
            <p className="mt-0.5 text-xs text-text-muted">
              {usage?.ai_monthly_request_quota != null ? `${usage.ai_monthly_request_quota.toLocaleString()} monthly limit` : "Unlimited"}
            </p>
          </SettingsCard>
        </div>
      </SettingsSection>

      <div className="grid gap-6 md:gap-4 lg:grid-cols-2">
        <SettingsSection index={2} title="Security" description="Protect this account.">
          <SettingsCard padding="none" className="md:p-6">
            <MobileActionRow icon={Lock} title="Password" description="Change your password" onClick={() => setPasswordOpen(true)} />
            <MobileActionRow icon={Monitor} title="Active sessions" description={sessionsLoading ? "Loading sessions…" : `${sessionCount} active session${sessionCount === 1 ? "" : "s"}`} onClick={() => setSessionsOpen(true)} />
            <div className="hidden md:block">
            <SettingsRow
              icon={Lock}
              title="Password"
              description="You will be signed out after changing it."
              action={
                <Button type="button" variant="outline" size="sm" onClick={() => setPasswordOpen(true)}>
                  Change password
                </Button>
              }
            />
            <div className="border-t border-surface-border" />
            <SettingsRow
              icon={Monitor}
              title="Active sessions"
              description={
                sessionsLoading
                  ? "Loading sessions…"
                  : `${sessionCount} active session${sessionCount === 1 ? "" : "s"}`
              }
              action={
                <Button type="button" variant="outline" size="sm" onClick={() => setSessionsOpen(true)}>
                  Manage sessions
                </Button>
              }
            />
            </div>
          </SettingsCard>
        </SettingsSection>

        <SettingsSection index={3} title="API Access" description="Tokens for non-browser clients.">
          <SettingsCard padding="none" className="md:p-6">
            <MobileActionRow icon={KeyRound} title="API tokens" description={tokensLoading ? "Loading tokens…" : `${tokenCount} active token${tokenCount === 1 ? "" : "s"}`} onClick={() => setTokensOpen(true)} />
            <div className="hidden md:block">
            <SettingsRow
              icon={KeyRound}
              title="API tokens"
              description={
                tokensLoading
                  ? "Loading tokens…"
                  : `${tokenCount} active token${tokenCount === 1 ? "" : "s"}`
              }
              action={
                <Button type="button" variant="outline" size="sm" onClick={() => setTokensOpen(true)}>
                  Manage tokens
                </Button>
              }
            />
            </div>
            <SettingsInfoBanner className="mt-3" tone="muted">
              Treat tokens like passwords. The secret is shown only once when a token is created.
            </SettingsInfoBanner>
          </SettingsCard>
        </SettingsSection>
      </div>

      {user?.is_admin && (
        <SettingsSection
          index={4}
          title="Administration"
          description="Manage people and access for this deployment."
          badge={<SettingsStatusBadge tone="info">Admin only</SettingsStatusBadge>}
        >
          <div className="divide-y divide-surface-border rounded-lg border border-surface-border bg-surface md:hidden">
            {[
              { to: "/settings/profile/users#users", icon: Users, title: "Users", description: "Roles and account status" },
              { to: "/settings/profile/users#invitations", icon: Mail, title: "Invitations", description: "Invite people to lesspaper-ngl" },
              { to: "/settings/profile/users#password-resets", icon: RotateCcw, title: "Password resets", description: "Approve reset requests" },
              { to: "/settings/profile/users#quotas", icon: Gauge, title: "Quotas", description: "Storage and AI limits" },
            ].map((item) => <MobileLinkRow key={item.to} {...item} />)}
          </div>
          <div className="hidden gap-3 md:grid md:grid-cols-2 xl:grid-cols-4">
            {[
              {
                to: "/settings/profile/users#users",
                icon: Users,
                title: "Users",
                description: "Roles and account status",
              },
              {
                to: "/settings/profile/users#invitations",
                icon: Mail,
                title: "Invitations",
                description: "Invite people to lesspaper-ngl",
              },
              {
                to: "/settings/profile/users#password-resets",
                icon: RotateCcw,
                title: "Password resets",
                description: "Approve reset requests",
              },
              {
                to: "/settings/profile/users#quotas",
                icon: Gauge,
                title: "Quotas",
                description: "Storage and AI limits",
              },
            ].map((item) => (
              <SettingsCard key={item.to} to={item.to} padding="sm" interactive>
                <div className="flex items-start gap-3">
                  <item.icon className="mt-0.5 h-[18px] w-[18px] text-text-secondary" strokeWidth={1.75} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-text-primary">{item.title}</p>
                    <p className="mt-0.5 text-xs text-text-secondary">{item.description}</p>
                  </div>
                  <ChevronRight className="h-4 w-4 text-text-muted" strokeWidth={1.75} aria-hidden="true" />
                </div>
              </SettingsCard>
            ))}
          </div>
        </SettingsSection>
      )}

      <Dialog
        open={passwordOpen}
        onOpenChange={(open) => {
          setPasswordOpen(open);
          if (!open) {
            setCurrentPassword("");
            setNewPassword("");
            setConfirmPassword("");
            setPasswordMsg(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Change password</DialogTitle>
            <DialogDescription>
              After changing your password you will be signed out and must sign in again.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-text-secondary">Current password</label>
              <Input
                type="password"
                className="mt-1"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary">New password</label>
              <Input
                type="password"
                className="mt-1"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary">Confirm new password</label>
              <Input
                type="password"
                className="mt-1"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>
            {passwordMsg && <p className="text-xs text-danger">{passwordMsg}</p>}
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setPasswordOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void savePassword()}
              disabled={
                changePassword.isPending ||
                !currentPassword ||
                newPassword.length < 8 ||
                !confirmPassword
              }
            >
              Change password
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={sessionsOpen} onOpenChange={setSessionsOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Active sessions</DialogTitle>
            <DialogDescription>Review and revoke devices signed in to your account.</DialogDescription>
          </DialogHeader>
          {sessions.filter((item) => !item.current).length > 0 && (
            <div className="mb-3 flex justify-end">
              <Button
                size="sm"
                variant="outline"
                onClick={() => signOutOthers.mutate()}
                disabled={signOutOthers.isPending}
              >
                Sign out other sessions
              </Button>
            </div>
          )}
          {sessionsLoading ? (
            <p className="text-sm text-text-muted">Loading sessions…</p>
          ) : sessions.length === 0 ? (
            <p className="text-sm text-text-muted">No active sessions found.</p>
          ) : (
            <ul className="divide-y divide-surface-border rounded-md border border-surface-border">
              {sessions.map((item) => (
                <li key={item.id} className="flex flex-wrap items-center gap-3 p-3 text-sm">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-text-primary">
                      {item.user_agent || "Unknown device"} {item.current && <strong>(current)</strong>}
                    </p>
                    <p className="text-xs text-text-muted">
                      Last active {new Date(item.last_seen_at).toLocaleString()}
                      {item.ip_address ? ` · ${item.ip_address}` : ""}
                    </p>
                  </div>
                  {!item.current && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => revokeSession.mutate(item.id)}
                      disabled={revokeSession.isPending}
                    >
                      Revoke
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={tokensOpen} onOpenChange={setTokensOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>API tokens</DialogTitle>
            <DialogDescription>
              Bearer tokens for MCP and other non-browser clients. The secret is shown only once.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-0 flex-1">
              <label className="text-xs text-text-secondary" htmlFor="token-name">
                Token name
              </label>
              <Input
                id="token-name"
                className="mt-1"
                aria-label="Token name"
                value={tokenName}
                onChange={(e) => setTokenName(e.target.value)}
                placeholder="Cursor"
              />
            </div>
            <Button
              type="button"
              size="sm"
              disabled={createApiToken.isPending || !tokenName.trim()}
              onClick={() => {
                void (async () => {
                  setTokenMsg(null);
                  try {
                    const created = await createApiToken.mutateAsync(tokenName.trim());
                    setNewTokenSecret(created.token);
                    setTokenName("");
                  } catch (err) {
                    setTokenMsg(err instanceof Error ? err.message : "Could not create token");
                  }
                })();
              }}
            >
              Create token
            </Button>
          </div>
          {newTokenSecret && (
            <div className="mt-3 rounded-md border border-accent/30 bg-accent-muted p-3 text-sm">
              <p className="mb-2 text-xs text-text-muted">Copy this secret now. It will not be shown again.</p>
              <code className="block break-all text-text-primary">{newTokenSecret}</code>
              <div className="mt-2 flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => void navigator.clipboard.writeText(newTokenSecret)}
                >
                  Copy
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setNewTokenSecret(null)}>
                  Done
                </Button>
              </div>
            </div>
          )}
          {tokenMsg && <p className="mt-2 text-xs text-danger">{tokenMsg}</p>}
          {tokensLoading ? (
            <p className="mt-3 text-sm text-text-muted">Loading tokens…</p>
          ) : apiTokens.length === 0 ? (
            <p className="mt-3 text-sm text-text-muted">No API tokens yet.</p>
          ) : (
            <ul className="mt-3 divide-y divide-surface-border rounded-md border border-surface-border">
              {apiTokens.map((item) => (
                <li key={item.id} className="flex flex-wrap items-center gap-3 p-3 text-sm">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-text-primary">
                      {item.name} <span className="text-text-muted">({item.prefix}…)</span>
                    </p>
                    <p className="text-xs text-text-muted">
                      Created {new Date(item.created_at).toLocaleString()}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => revokeApiToken.mutate(item.id)}
                    disabled={revokeApiToken.isPending}
                  >
                    Revoke
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </DialogContent>
      </Dialog>
    </SettingsContent>
  );
}

function MobileActionRow({
  icon: Icon,
  title,
  description,
  onClick,
}: {
  icon: typeof Lock;
  title: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} className="flex min-h-16 w-full items-center gap-3 px-4 py-2 text-left first:rounded-t-lg last:rounded-b-lg hover:bg-surface-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-accent">
      <Icon className="h-5 w-5 shrink-0 text-text-secondary" strokeWidth={1.75} aria-hidden="true" />
      <span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-text-primary">{title}</span><span className="mt-0.5 block text-xs text-text-secondary">{description}</span></span>
      <ChevronRight className="h-5 w-5 shrink-0 text-text-muted" aria-hidden="true" />
    </button>
  );
}

function MobileLinkRow({ icon: Icon, title, description, to }: { icon: typeof Users; title: string; description: string; to: string }) {
  return (
    <Link to={to} className="flex min-h-16 w-full items-center gap-3 px-4 py-2 text-left hover:bg-surface-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-accent">
      <Icon className="h-5 w-5 shrink-0 text-text-secondary" strokeWidth={1.75} aria-hidden="true" />
      <span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-text-primary">{title}</span><span className="mt-0.5 block text-xs text-text-secondary">{description}</span></span>
      <ChevronRight className="h-5 w-5 shrink-0 text-text-muted" aria-hidden="true" />
    </Link>
  );
}
