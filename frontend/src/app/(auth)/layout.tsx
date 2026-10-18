export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex flex-1 flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-1 text-center">
          <p className="text-xl font-semibold tracking-tight">Psylink</p>
          <p className="text-sm text-muted-foreground">Your voice, between sessions</p>
        </div>
        {children}
        <p className="text-center text-xs text-muted-foreground">
          Psylink is not emergency care. In an emergency, contact local emergency services.
        </p>
      </div>
    </main>
  );
}
