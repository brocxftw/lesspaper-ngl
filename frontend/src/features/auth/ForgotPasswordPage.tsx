import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link } from "react-router-dom";
import { Leaf } from "lucide-react";
import { useForgotPassword } from "@/lib/api/hooks";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ApiError } from "@/lib/api/client";

const schema = z.object({
  username: z.string().min(1, "Username is required"),
});

type Form = z.infer<typeof schema>;

export function ForgotPasswordPage() {
  const forgot = useForgotPassword();
  const {
    register,
    handleSubmit,
    formState: { errors },
    setError,
  } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: { username: "" },
  });

  const onSubmit = async (data: Form) => {
    try {
      const result = await forgot.mutateAsync(data.username.trim());
      setError("root", { type: "success", message: result.message });
    } catch (err) {
      setError("root", {
        message: err instanceof ApiError ? err.message : "Request failed",
      });
    }
  };

  const isSuccess = errors.root?.type === "success";

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-muted p-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="inline-flex items-center gap-2 mb-2">
            <Leaf className="h-7 w-7 text-accent" />
            <span className="text-2xl font-semibold text-text-primary tracking-tight">
              lesspaper-ngl
            </span>
          </div>
          <p className="text-sm text-text-secondary">Request a password reset</p>
        </div>

        <form
          onSubmit={handleSubmit(onSubmit)}
          className="rounded-lg border border-surface-border bg-surface p-6 shadow-sm space-y-4"
        >
          <p className="text-xs text-text-muted">
            An administrator must approve your request, then they will share a one-time reset
            link with you. lesspaper-ngl does not send email yet.
          </p>
          <div>
            <label htmlFor="username" className="text-xs font-medium text-text-secondary">
              Username
            </label>
            <Input
              id="username"
              autoComplete="username"
              className="mt-1"
              {...register("username")}
            />
            {errors.username && (
              <p className="mt-1 text-xs text-danger">{errors.username.message}</p>
            )}
          </div>

          {errors.root && (
            <p className={`text-xs text-center ${isSuccess ? "text-text-secondary" : "text-danger"}`}>
              {errors.root.message}
            </p>
          )}

          <Button type="submit" className="w-full" disabled={forgot.isPending || isSuccess}>
            {forgot.isPending ? "Submitting…" : "Request reset"}
          </Button>

          <p className="text-center text-xs text-text-secondary">
            <Link to="/login" className="text-accent hover:underline">
              Back to sign in
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
