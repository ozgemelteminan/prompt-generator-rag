import type { AppLanguage } from "@/lib/api";

export type TaskPreset = {
  id: string;
  title: Record<AppLanguage, string>;
  description: Record<AppLanguage, string>;
};

export const taskPresets: TaskPreset[] = [
  {
    id: "write-email",
    title: { tr: "E-posta yaz", en: "Write an email" },
    description: { tr: "Açık ve etkili bir e-posta hazırlayın.", en: "Draft a clear, effective email." },
  },
  {
    id: "research-topic",
    title: { tr: "Bir konuyu araştır", en: "Research a topic" },
    description: { tr: "Bir konuyu keşfedin ve değerlendirin.", en: "Explore and assess a topic." },
  },
  {
    id: "analyze",
    title: { tr: "Bir şeyi analiz et", en: "Analyze something" },
    description: { tr: "Bir durumu veya metni inceleyin.", en: "Examine a situation or text." },
  },
  {
    id: "debug-code",
    title: { tr: "Kodu hata ayıkla", en: "Debug code" },
    description: { tr: "Bir kod sorununu çözün.", en: "Work through a code issue." },
  },
  {
    id: "learn-topic",
    title: { tr: "Bir konuyu öğren", en: "Learn a topic" },
    description: { tr: "Bir konunun net açıklamasını alın.", en: "Get a clear explanation of a topic." },
  },
  {
    id: "summarize",
    title: { tr: "İçeriği özetle", en: "Summarize content" },
    description: { tr: "Ana noktaları kısa bir özete dönüştürün.", en: "Turn content into a concise summary." },
  },
  {
    id: "brainstorm",
    title: { tr: "Fikir üret", en: "Brainstorm ideas" },
    description: { tr: "Yeni fikirler ve seçenekler oluşturun.", en: "Generate ideas and options." },
  },
  {
    id: "make-plan",
    title: { tr: "Plan yap", en: "Make a plan" },
    description: { tr: "Uygulanabilir bir plan oluşturun.", en: "Create an actionable plan." },
  },
  {
    id: "translate",
    title: { tr: "Çeviri yap", en: "Translate" },
    description: { tr: "Metni istediğiniz dile çevirin.", en: "Translate text into the needed language." },
  },
  {
    id: "work-with-data",
    title: { tr: "Verilerle çalış", en: "Work with data" },
    description: { tr: "Veriyi analiz edin veya dönüştürün.", en: "Analyze or transform data." },
  },
];
