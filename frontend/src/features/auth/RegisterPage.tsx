import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useRegister, useRegistrationStatus } from "@/lib/api/hooks";
import { BrandLockup } from "@/components/brand/BrandMark";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

const registerSchema = z.object({
  username: z
    .string()
    .min(3, "At least 3 characters")
    .max(32)
    .regex(/^[a-zA-Z0-9_]+$/, "Letters, numbers, and underscores only"),
  display_name: z.string().max(128).optional(),
  password: z.string().min(8, "At least 8 characters"),
});

type RegisterForm = z.infer<typeof registerSchema>;

export function RegisterPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const invite = params.get("invite") ?? undefined;
  const { data: status } = useRegistrationStatus();
  const registerMut = useRegister();

  const {
    register,
    handleSubmit,
    formState: { errors },
    setError,
  } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
    defaultValues: { username: "", display_name: "", password: "" },
  });

  const registrationClosed = status && !status.allow_registration && !invite;

  const onSubmit = async (data: RegisterForm) => {
    try {
      await registerMut.mutateAsync({
        username: data.username,
        password: data.password,
        display_name: data.display_name || data.username,
        invite_token: invite,
      });
      navigate("/documents", { replace: true });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not create account";
      setError("root", { message });
    }
  };

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
          <p className="text-sm text-text-secondary">Create your private library</p>
        </div>

        {registrationClosed ? (
          <div className="rounded-lg border border-surface-border bg-surface p-6 text-center space-y-3">
            <p className="text-sm text-text-secondary">
              Open registration is disabled. Ask an admin for an invite link.
            </p>
            <Link to="/login" className="text-sm text-accent hover:underline">
              Back to sign in
            </Link>
          </div>
        ) : (
          <form
            onSubmit={handleSubmit(onSubmit)}
            className="rounded-lg border border-surface-border bg-surface p-6 shadow-sm space-y-4"
          >
            {invite && (
              <p className="text-xs text-text-secondary rounded bg-surface-muted px-2 py-1.5">
                Signing up with an invite
              </p>
            )}
            <div>
              <label htmlFor="username" className="text-xs font-medium text-text-secondary">
                Username
              </label>
              <Input id="username" className="mt-1" autoComplete="username" {...register("username")} />
              {errors.username && (
                <p className="mt-1 text-xs text-danger">{errors.username.message}</p>
              )}
            </div>
            <div>
              <label htmlFor="display_name" className="text-xs font-medium text-text-secondary">
                Display name
              </label>
              <Input id="display_name" className="mt-1" {...register("display_name")} />
            </div>
            <div>
              <label htmlFor="password" className="text-xs font-medium text-text-secondary">
                Password
              </label>
              <Input
                id="password"
                type="password"
                className="mt-1"
                autoComplete="new-password"
                {...register("password")}
              />
              {errors.password && (
                <p className="mt-1 text-xs text-danger">{errors.password.message}</p>
              )}
            </div>
            {errors.root && (
              <p className="text-xs text-danger text-center">{errors.root.message}</p>
            )}
            <Button type="submit" className="w-full" disabled={registerMut.isPending}>
              {registerMut.isPending ? "Creating account…" : "Create account"}
            </Button>
            <p className="text-center text-xs text-text-secondary">
              Already have an account?{" "}
              <Link to="/login" className="text-accent hover:underline">
                Sign in
              </Link>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
