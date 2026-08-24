import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useResetPassword, useValidateResetToken } from "@/lib/api/hooks";
import { BrandLockup } from "@/components/brand/BrandMark";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ApiError } from "@/lib/api/client";

const schema = z
  .object({
    new_password: z.string().min(8, "Password must be at least 8 characters"),
    confirm_password: z.string().min(1, "Confirm your password"),
  })
  .refine((data) => data.new_password === data.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  });

type Form = z.infer<typeof schema>;

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const navigate = useNavigate();
  const { data: validation, isLoading } = useValidateResetToken(token);
  const reset = useResetPassword();

  const {
    register,
    handleSubmit,
    formState: { errors },
    setError,
  } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: { new_password: "", confirm_password: "" },
  });

  const onSubmit = async (data: Form) => {
    if (!token) return;
    try {
      await reset.mutateAsync({ token, new_password: data.new_password });
      navigate("/login", {
        replace: true,
        state: { notice: "Password updated. Sign in with your new password." },
      });
    } catch (err) {
      setError("root", {
        message: err instanceof ApiError ? err.message : "Reset failed",
      });
    }
  };

  const invalid = !token || (!isLoading && validation && !validation.valid);

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-muted p-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mb-2">
            <BrandLockup
              variant="on-light"
              markSize={28}
              wordmarkClassName="text-2xl font-semibold"
            />
          </div>
          <p className="text-sm text-text-secondary">Choose a new password</p>
        </div>

        <div className="rounded-lg border border-surface-border bg-surface p-6 shadow-sm space-y-4">
          {isLoading && <p className="text-sm text-text-muted text-center">Checking link…</p>}

          {invalid && !isLoading && (
            <>
              <p className="text-sm text-danger text-center">
                This reset link is invalid or has expired. Request a new one from the sign-in page.
              </p>
              <p className="text-center text-xs text-text-secondary">
                <Link to="/forgot-password" className="text-accent hover:underline">
                  Request reset
                </Link>
                {" · "}
                <Link to="/login" className="text-accent hover:underline">
                  Sign in
                </Link>
              </p>
            </>
          )}

          {!invalid && !isLoading && (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              {validation?.username && (
                <p className="text-xs text-text-secondary text-center">
                  Resetting password for <span className="font-medium">@{validation.username}</span>
                </p>
              )}
              <div>
                <label htmlFor="new_password" className="text-xs font-medium text-text-secondary">
                  New password
                </label>
                <Input
                  id="new_password"
                  type="password"
                  autoComplete="new-password"
                  className="mt-1"
                  {...register("new_password")}
                />
                {errors.new_password && (
                  <p className="mt-1 text-xs text-danger">{errors.new_password.message}</p>
                )}
              </div>
              <div>
                <label
                  htmlFor="confirm_password"
                  className="text-xs font-medium text-text-secondary"
                >
                  Confirm password
                </label>
                <Input
                  id="confirm_password"
                  type="password"
                  autoComplete="new-password"
                  className="mt-1"
                  {...register("confirm_password")}
                />
                {errors.confirm_password && (
                  <p className="mt-1 text-xs text-danger">{errors.confirm_password.message}</p>
                )}
              </div>
              {errors.root && (
                <p className="text-xs text-danger text-center">{errors.root.message}</p>
              )}
              <Button type="submit" className="w-full" disabled={reset.isPending}>
                {reset.isPending ? "Saving…" : "Set new password"}
              </Button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
