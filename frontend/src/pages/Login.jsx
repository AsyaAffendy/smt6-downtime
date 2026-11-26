import { Field, Form } from "../components/ui";
import { useAuth } from "../lib/auth";

export default function Login() {
  const { login } = useAuth();
  return (
    <main className="mx-auto w-full max-w-sm p-6">
      <Form className="panel p-6" submit="Sign in" onSubmit={(d) => login(d.username, d.password)}>
        <h1 className="text-xl font-bold">Authorised sign-in</h1>
        <Field label="Username"><input name="username" required autoFocus autoComplete="username" className="input" /></Field>
        <Field label="Password"><input name="password" type="password" required autoComplete="current-password" className="input" /></Field>
      </Form>
    </main>
  );
}
