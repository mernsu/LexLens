import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LexLens",
  description: "建设工程合同纠纷法律研究工作台",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
