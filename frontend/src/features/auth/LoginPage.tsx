import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Eye, EyeOff, Lock, User } from "lucide-react";
import { useHealth, useLogin, useRegistrationStatus } from "@/lib/api/hooks";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { BrandMark, BrandWordmark } from "@/components/brand/BrandMark";
import bgLogin from "@/assets/brand/bg_login_2.svg";

const loginSchema = z.object({
  username: z.string().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
});

type LoginForm = z.infer<typeof loginSchema>;

const fieldClassName =
  "h-[52px] rounded-[12px] border-surface-border bg-white " +
  "text-[14px] text-text-primary placeholder:text-text-muted " +
  "focus-visible:border-accent/70 focus-visible:ring-0 " +
  "focus-visible:shadow-[0_0_0_3px_var(--color-accent-ring)]";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [showPassword, setShowPassword] = useState(false);
  const notice =
    typeof location.state === "object" &&
    location.state &&
    "notice" in location.state &&
    typeof (location.state as { notice?: unknown }).notice === "string"
      ? (location.state as { notice: string }).notice
      : null;
  const login = useLogin();
  const { data: regStatus } = useRegistrationStatus();
  const { data: health } = useHealth();
  const version = health?.version?.trim();

  const {
    register,
    handleSubmit,
    formState: { errors },
    setError,
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: "", password: "" },
  });

  const onSubmit = async (data: LoginForm) => {
    try {
      await login.mutateAsync(data);
      const from =
        typeof location.state === "object" && location.state && "from" in location.state
          ? (location.state as { from?: { pathname?: string; search?: string; hash?: string } }).from
          : undefined;
      const destination = from?.pathname
        ? `${from.pathname}${from.search ?? ""}${from.hash ?? ""}`
        : "/inbox";
      navigate(destination, { replace: true });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Invalid username or password";
      setError("root", { message });
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#F8FAFC] p-6">
      <img
        src={bgLogin}
        alt=""
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 h-full w-full object-cover object-center"
      />

      <div
        className={cn(
          "relative z-10 w-full max-w-full rounded-[24px] border border-surface-border",
          "bg-white px-5 py-7 text-text-primary",
          "shadow-[0_10px_30px_rgba(15,23,42,0.08),0_2px_8px_rgba(15,23,42,0.06)]",
          "sm:max-w-[520px] sm:p-8",
          "lg:max-w-[560px] lg:px-12 lg:pt-10 lg:pb-8",
        )}
      >
        <div className="flex flex-col items-center gap-1.5 text-center">
          <div className="flex items-center gap-3">
            <BrandMark variant="on-light" size={56} />
            <h1 className="text-[40px] leading-none font-bold tracking-[-0.03em] sm:text-[52px]">
              <BrandWordmark variant="on-light" />
            </h1>
          </div>
          <div className="flex items-center justify-center gap-[9px]">
            {version ? (
              <span className="inline-flex h-[32px] items-center rounded-[9px] border border-accent bg-white px-[14px] text-[13px] font-semibold text-accent">
                v{version.replace(/^v/i, "")}
              </span>
            ) : null}
          </div>
        </div>

        <div className="mt-[29px] mb-7 text-center">
          <h2 className="text-2xl font-semibold text-text-primary">Welcome back</h2>
          <p className="mt-1 text-base font-normal text-text-secondary">
            Sign in to access your documents
          </p>
        </div>

        <form className="space-y-5" onSubmit={handleSubmit(onSubmit)}>
          {notice && (
            <p className="rounded-lg bg-surface-muted px-3 py-2 text-sm text-text-secondary">
              {notice}
            </p>
          )}

          <div>
            <label
              htmlFor="username"
              className="text-sm font-semibold text-text-primary"
            >
              Username
            </label>
            <div className="relative mt-1.5">
              <User
                className="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-text-muted"
                aria-hidden="true"
              />
              <Input
                id="username"
                autoComplete="username"
                placeholder="Enter your username"
                className={cn(fieldClassName, "pl-11")}
                {...register("username")}
              />
            </div>
            {errors.username && (
              <p className="mt-1 text-xs text-danger">{errors.username.message}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="password"
              className="text-sm font-semibold text-text-primary"
            >
              Password
            </label>
            <div className="relative mt-1.5">
              <Lock
                className="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-text-muted"
                aria-hidden="true"
              />
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                placeholder="Enter your password"
                className={cn(fieldClassName, "pr-11 pl-11")}
                {...register("password")}
              />
              <button
                type="button"
                className="absolute top-1/2 right-3.5 -translate-y-1/2 text-text-muted transition-colors hover:text-text-primary"
                aria-label={showPassword ? "Hide password" : "Show password"}
                onClick={() => setShowPassword((open) => !open)}
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <Eye className="h-4 w-4" aria-hidden="true" />
                )}
              </button>
            </div>
            {errors.password && (
              <p className="mt-1 text-xs text-danger">{errors.password.message}</p>
            )}
            <p className="mt-2 text-right">
              <Link
                to="/forgot-password"
                className="text-sm font-medium text-accent transition-colors hover:text-accent-hover"
              >
                Forgot password?
              </Link>
            </p>
          </div>

          {errors.root && (
            <p className="text-center text-xs text-danger">{errors.root.message}</p>
          )}

          <Button
            type="submit"
            disabled={login.isPending}
            className={cn(
              "mt-2 h-[54px] w-full rounded-[12px] border-0 bg-[#0F172A] text-lg font-semibold text-white shadow-none",
              "hover:bg-[#1E293B] hover:shadow-none",
            )}
          >
            {login.isPending ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="mt-5 text-center text-sm font-normal text-[#94A3B8]">
          Self-hosted. Your data stays under your control.
        </p>

        {(regStatus?.allow_registration ?? true) && (
          <p className="mt-3 text-center text-sm text-[#94A3B8]">
            New here?{" "}
            <Link
              to="/register"
              className="font-medium text-accent transition-colors hover:text-accent-hover"
            >
              Create an account
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}
