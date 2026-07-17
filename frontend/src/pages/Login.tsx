import React, { useState } from "react";
import { motion } from "framer-motion";
import {
  FiArrowRight,
  FiCheck,
  FiFileText,
  FiLock,
  FiShield,
  FiZap,
} from "react-icons/fi";
import api from "../api";
import ThemeToggle from "../components/ThemeToggle";
import { getApiErrorDetail, getApiErrorStatus } from "../utils/errorUtils";

interface LoginProps {
  onLoginSuccess: () => void;
}

const Login: React.FC<LoginProps> = ({ onLoginSuccess }) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isTwoFactorInfo, setIsTwoFactorInfo] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setIsLoading(true);

    const formData = new FormData();
    formData.append("username", username);
    formData.append("password", password);
    if (otp) formData.append("client_secret", otp);

    try {
      await api.post("/token", formData, { withCredentials: true });
      onLoginSuccess();
    } catch (err: unknown) {
      const status = getApiErrorStatus(err);
      const detail = getApiErrorDetail(err);
      if (
        status === 401 &&
        detail === "2FA Required"
      ) {
        setIsTwoFactorInfo(true);
        setError("Two-Factor Authentication Required");
      } else if (
        status === 401 &&
        detail === "Invalid 2FA Code"
      ) {
        setError("Invalid Code. Please try again.");
      } else {
        setError("Invalid credentials");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#070907] text-white">
      <div className="ambient-grid absolute inset-0 opacity-50" />
      <div className="absolute -left-32 top-[-12rem] h-[34rem] w-[34rem] rounded-full bg-[#b8f15a]/10 blur-[120px]" />
      <div
        className={[
          "absolute -bottom-52 right-[-8rem] h-[40rem] w-[40rem] rounded-full",
          "bg-[#7397ff]/10 blur-[140px]",
        ].join(" ")}
      />
      <ThemeToggle className="absolute right-5 top-5 z-20 sm:right-8 sm:top-8" />

      <div className="relative mx-auto grid min-h-screen max-w-[1500px] lg:grid-cols-[1.1fr_0.9fr]">
        <section
          className={[
            "hidden border-r border-white/[0.07] px-12 py-10 lg:flex lg:flex-col",
            "lg:justify-between xl:px-20",
          ].join(" ")}
        >
          <div className="flex items-center gap-3">
            <div
              className={[
                "flex h-10 w-10 items-center justify-center rounded-2xl bg-[#b8f15a]",
                "text-[#10130c] shadow-[0_0_35px_rgba(184,241,90,0.2)]",
              ].join(" ")}
            >
              <FiFileText size={20} />
            </div>
            <div>
              <p className="text-sm font-bold tracking-[0.16em]">ATLAS</p>
              <p className="text-xs text-white/40">Document Intelligence</p>
            </div>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55 }}
            className="max-w-2xl"
          >
            <span className="chip mb-6 border-[#b8f15a]/20 bg-[#b8f15a]/[0.06] text-[#b8f15a]">
              <FiZap /> AI-powered workspace
            </span>
            <h1 className="max-w-xl text-5xl font-semibold leading-[1.04] tracking-[-0.055em] xl:text-7xl">
              Dokumente rein.
              <br />
              <span className="text-white/38">Klarheit raus.</span>
            </h1>
            <p className="mt-7 max-w-lg text-lg leading-8 text-white/52">
              Verträge und Rechnungen in einem fokussierten Workspace
              analysieren, organisieren und sicher verwalten.
            </p>
            <div className="mt-10 grid max-w-xl grid-cols-3 gap-3">
              {[
                [FiZap, "AI Analyse", "Direkt aus PDFs"],
                [FiShield, "Geschützt", "Granulare Rechte"],
                [FiCheck, "Im Blick", "Fristen & Werte"],
              ].map(([Icon, title, copy]) => {
                const FeatureIcon = Icon as typeof FiZap;
                return (
                  <div
                    key={title as string}
                    className="rounded-2xl border border-white/[0.07] bg-white/[0.025] p-4 backdrop-blur-xl"
                  >
                    <FeatureIcon className="mb-5 text-[#b8f15a]" />
                    <p className="text-sm font-semibold">{title as string}</p>
                    <p className="mt-1 text-xs text-white/36">
                      {copy as string}
                    </p>
                  </div>
                );
              })}
            </div>
          </motion.div>

          <p className="text-xs text-white/28">
            Private Infrastruktur · Geschützter Zugriff
          </p>
        </section>

        <section className="flex min-h-screen items-center justify-center px-5 py-10 sm:px-10">
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.4 }}
            className="w-full max-w-md"
          >
            <div className="mb-10 flex items-center gap-3 lg:hidden">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#b8f15a] text-[#10130c]">
                <FiFileText />
              </div>
              <span className="font-bold tracking-[0.14em]">ATLAS</span>
            </div>

            <p className="eyebrow">Secure access</p>
            <h2 className="mt-3 text-4xl font-semibold tracking-[-0.045em]">
              {isTwoFactorInfo ? "Identität bestätigen" : "Welcome Back"}
            </h2>
            <p className="mt-3 text-sm leading-6 text-white/45">
              {isTwoFactorInfo
                ? "Gib den sechsstelligen Code aus deiner Authenticator-App ein."
                : "Melde dich an und übernimm wieder die Kontrolle über deine Dokumente."}
            </p>

            {error && (
              <div
                className={[
                  "mt-6 rounded-2xl border border-rose-400/20 bg-rose-400/[0.07] px-4 py-3",
                  "text-sm text-rose-200",
                ].join(" ")}
                role="alert"
              >
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="mt-8 space-y-5">
              {!isTwoFactorInfo ? (
                <>
                  <label className="block">
                    <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.12em] text-white/40">
                      Username
                    </span>
                    <input
                      className="field h-13"
                      type="text"
                      value={username}
                      onChange={(event) => setUsername(event.target.value)}
                      placeholder="Enter your username"
                      autoComplete="username"
                      required
                    />
                  </label>
                  <label className="block">
                    <span
                      className={[
                        "mb-2 flex items-center gap-2 text-xs font-semibold uppercase",
                        "tracking-[0.12em] text-white/40",
                      ].join(" ")}
                    >
                      <FiLock /> Password
                    </span>
                    <input
                      className="field h-13"
                      type="password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      placeholder="••••••••"
                      autoComplete="current-password"
                      required
                    />
                  </label>
                </>
              ) : (
                <label className="block">
                  <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.12em] text-white/40">
                    Authenticator Code
                  </span>
                  <input
                    className="field h-16 text-center text-2xl font-semibold tracking-[0.4em]"
                    type="text"
                    inputMode="numeric"
                    value={otp}
                    onChange={(event) =>
                      setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))
                    }
                    placeholder="000 000"
                    maxLength={6}
                    autoFocus
                    required
                  />
                </label>
              )}

              <button
                type="submit"
                disabled={isLoading}
                className="btn-primary h-13 w-full justify-between px-5"
              >
                <span>
                  {isLoading
                    ? "Verifying..."
                    : isTwoFactorInfo
                      ? "Verify Code"
                      : "Sign In"}
                </span>
                <FiArrowRight />
              </button>
              {isTwoFactorInfo && (
                <button
                  type="button"
                  onClick={() => {
                    setIsTwoFactorInfo(false);
                    setError("");
                  }}
                  className="btn-ghost w-full"
                >
                  Back to Login
                </button>
              )}
            </form>
          </motion.div>
        </section>
      </div>
    </main>
  );
};

export default Login;
