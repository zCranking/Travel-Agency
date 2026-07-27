"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabaseBrowserClient } from "@/lib/supabase";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const { data, error } = await supabaseBrowserClient.auth.signInWithPassword({
      email,
      password,
    });
    if (error) {
      setError(error.message);
      return;
    }

    const { data: employee } = await supabaseBrowserClient
      .from("employees")
      .select("id")
      .eq("auth_user_id", data.user.id)
      .single();

    const { data: trip } = employee
      ? await supabaseBrowserClient
          .from("trips")
          .select("id")
          .eq("employee_id", employee.id)
          .limit(1)
          .single()
      : { data: null };

    router.push(trip ? `/chat/${trip.id}` : "/itinerary");
  }

  return (
    <form onSubmit={handleSubmit}>
      <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
      />
      {error && <p>{error}</p>}
      <button type="submit">Sign in</button>
    </form>
  );
}
