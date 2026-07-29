"use client";

import { useEffect, useState } from "react";
import { supabaseBrowserClient } from "@/lib/supabase";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";

type TravelerProfile = { phone_number?: string } | null;

type Employee = {
  id: string;
  name: string;
  email: string;
  traveler_profile: TravelerProfile;
};

const inputClass =
  "rounded-md border border-black/10 bg-white px-3 py-2 font-sans text-sm text-[var(--color-ink)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-amber)]";

export default function ProfilePage() {
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [newPassword, setNewPassword] = useState("");
  const [changingPassword, setChangingPassword] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSaved, setPasswordSaved] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      const {
        data: { user },
      } = await supabaseBrowserClient.auth.getUser();
      if (!user) {
        setLoadError("Sign in to view your profile.");
        setLoading(false);
        return;
      }
      const { data, error } = await supabaseBrowserClient
        .from("employees")
        .select("id, name, email, traveler_profile")
        .eq("auth_user_id", user.id)
        .maybeSingle();
      if (!active) return;
      if (error) {
        setLoadError(error.message);
        setLoading(false);
        return;
      }
      if (data) {
        const row = data as Employee;
        setEmployee(row);
        setName(row.name);
        setPhone(row.traveler_profile?.phone_number ?? "");
      }
      setLoading(false);
    })();
    return () => {
      active = false;
    };
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!employee) return;
    setSaving(true);
    setSaveError(null);
    setSaved(false);

    const traveler_profile = {
      ...(employee.traveler_profile ?? {}),
      phone_number: phone.trim() || undefined,
    };
    const { error } = await supabaseBrowserClient
      .from("employees")
      .update({ name, traveler_profile })
      .eq("id", employee.id);

    setSaving(false);
    if (error) {
      setSaveError(error.message);
      return;
    }
    setEmployee({ ...employee, name, traveler_profile });
    setSaved(true);
  }

  async function handlePasswordChange(e: React.FormEvent) {
    e.preventDefault();
    if (newPassword.length < 6) {
      setPasswordError("Password must be at least 6 characters.");
      return;
    }
    setChangingPassword(true);
    setPasswordError(null);
    setPasswordSaved(false);

    const { error } = await supabaseBrowserClient.auth.updateUser({
      password: newPassword,
    });

    setChangingPassword(false);
    if (error) {
      setPasswordError(error.message);
      return;
    }
    setNewPassword("");
    setPasswordSaved(true);
  }

  return (
    <AppShell title="Profile" meta="Account settings">
      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-7">
        {loading && (
          <div className="flex max-w-[480px] flex-col gap-3">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-11 animate-pulse rounded-lg bg-[rgba(27,42,65,0.05)]"
              />
            ))}
          </div>
        )}

        {!loading && loadError && (
          <p role="alert" className="font-sans text-sm text-[var(--color-coral)]">
            {loadError}
          </p>
        )}

        {!loading && employee && (
          <div className="flex max-w-[480px] flex-col gap-6">
            <form
              onSubmit={handleSave}
              className="flex flex-col gap-4 rounded-xl border border-[var(--color-line)] bg-white p-6"
            >
              <h2 className="font-display text-lg font-semibold text-[var(--color-ink)]">
                Basic info
              </h2>

              <label className="flex flex-col gap-1.5">
                <span className="font-mono text-xs tracking-wide text-[var(--color-slate)] uppercase">
                  Name
                </span>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  className={inputClass}
                />
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="font-mono text-xs tracking-wide text-[var(--color-slate)] uppercase">
                  Email
                </span>
                <input
                  value={employee.email}
                  disabled
                  className={`${inputClass} bg-[#f4f2ee] text-[var(--color-slate)]`}
                />
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="font-mono text-xs tracking-wide text-[var(--color-slate)] uppercase">
                  Phone
                </span>
                <input
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+1 555 555 0100"
                  className={inputClass}
                />
              </label>

              {saveError && (
                <p role="alert" className="font-sans text-sm text-[var(--color-coral)]">
                  {saveError}
                </p>
              )}
              {saved && (
                <p className="font-sans text-sm text-[var(--color-teal)]">Saved.</p>
              )}

              <Button type="submit" disabled={saving} className="self-start">
                {saving ? "Saving…" : "Save changes"}
              </Button>
            </form>

            <form
              onSubmit={handlePasswordChange}
              className="flex flex-col gap-4 rounded-xl border border-[var(--color-line)] bg-white p-6"
            >
              <h2 className="font-display text-lg font-semibold text-[var(--color-ink)]">
                Password
              </h2>

              <label className="flex flex-col gap-1.5">
                <span className="font-mono text-xs tracking-wide text-[var(--color-slate)] uppercase">
                  New password
                </span>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  className={inputClass}
                />
              </label>

              {passwordError && (
                <p role="alert" className="font-sans text-sm text-[var(--color-coral)]">
                  {passwordError}
                </p>
              )}
              {passwordSaved && (
                <p className="font-sans text-sm text-[var(--color-teal)]">
                  Password updated.
                </p>
              )}

              <Button
                type="submit"
                variant="secondary"
                disabled={changingPassword}
                className="self-start"
              >
                {changingPassword ? "Updating…" : "Update password"}
              </Button>
            </form>
          </div>
        )}
      </div>
    </AppShell>
  );
}
