import { AppSidebar } from "@/components/layout/sidebar";

export default function MainLayout({ children }: { children: React.ReactNode }) {
  return (
    // `app-shell` exists for the print stylesheet: this wrapper is 100vh with
    // overflow hidden (content scrolls inside <main>), which means the print
    // engine sees exactly one viewport and silently clips the rest — the PDF
    // came out as page 1 only. @media print flattens it back into normal
    // document flow so the report paginates.
    <div className="app-shell flex h-screen overflow-hidden">
      <AppSidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="p-6 max-w-7xl mx-auto">{children}</div>
      </main>
    </div>
  );
}
