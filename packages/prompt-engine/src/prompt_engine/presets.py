"""Built-in, provider-independent quick-start task presets."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class LocalizedText(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    tr: str
    en: str


class TaskPreset(BaseModel):
    """Lightweight defaults supplied to analysis; never a prewritten final prompt."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    task_type_hint: str
    title: LocalizedText
    description: LocalizedText
    output_format_hint: str | None = None


TASK_PRESETS: tuple[TaskPreset, ...] = (
    TaskPreset(
        id="write-email",
        task_type_hint="writing.email",
        output_format_hint="email",
        title={"tr": "E-posta yaz", "en": "Write an email"},
        description={
            "tr": "Açık ve etkili bir e-posta hazırlayın.",
            "en": "Draft a clear, effective email.",
        },
    ),
    TaskPreset(
        id="research-topic",
        task_type_hint="research",
        title={"tr": "Bir konuyu araştır", "en": "Research a topic"},
        description={
            "tr": "Bir konuyu keşfedin ve değerlendirin.",
            "en": "Explore and assess a topic.",
        },
    ),
    TaskPreset(
        id="analyze",
        task_type_hint="analysis",
        title={"tr": "Bir şeyi analiz et", "en": "Analyze something"},
        description={
            "tr": "Bir durumu veya metni inceleyin.",
            "en": "Examine a situation or text.",
        },
    ),
    TaskPreset(
        id="debug-code",
        task_type_hint="coding.debug",
        title={"tr": "Kodu hata ayıkla", "en": "Debug code"},
        description={"tr": "Bir kod sorununu çözün.", "en": "Work through a code issue."},
    ),
    TaskPreset(
        id="learn-topic",
        task_type_hint="learning",
        title={"tr": "Bir konuyu öğren", "en": "Learn a topic"},
        description={
            "tr": "Bir konunun net açıklamasını alın.",
            "en": "Get a clear explanation of a topic.",
        },
    ),
    TaskPreset(
        id="summarize",
        task_type_hint="summarization",
        title={"tr": "İçeriği özetle", "en": "Summarize content"},
        description={
            "tr": "Ana noktaları kısa bir özete dönüştürün.",
            "en": "Turn content into a concise summary.",
        },
    ),
    TaskPreset(
        id="brainstorm",
        task_type_hint="brainstorming",
        title={"tr": "Fikir üret", "en": "Brainstorm ideas"},
        description={
            "tr": "Yeni fikirler ve seçenekler oluşturun.",
            "en": "Generate ideas and options.",
        },
    ),
    TaskPreset(
        id="make-plan",
        task_type_hint="planning",
        title={"tr": "Plan yap", "en": "Make a plan"},
        description={"tr": "Uygulanabilir bir plan oluşturun.", "en": "Create an actionable plan."},
    ),
    TaskPreset(
        id="translate",
        task_type_hint="translation",
        title={"tr": "Çeviri yap", "en": "Translate"},
        description={
            "tr": "Metni istediğiniz dile çevirin.",
            "en": "Translate text into the needed language.",
        },
    ),
    TaskPreset(
        id="work-with-data",
        task_type_hint="data",
        title={"tr": "Verilerle çalış", "en": "Work with data"},
        description={
            "tr": "Veriyi analiz edin veya dönüştürün.",
            "en": "Analyze or transform data.",
        },
    ),
)


def get_task_preset(preset_id: str) -> TaskPreset | None:
    return next((preset for preset in TASK_PRESETS if preset.id == preset_id), None)
