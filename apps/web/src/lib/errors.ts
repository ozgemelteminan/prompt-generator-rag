import type { ApiErrorDetails, AppLanguage } from "./api";

const messages = {
  tr: {
    invalid_request: "Lütfen girdiğiniz bilgileri kontrol edin.",
    analysis_unavailable: "İsteğinizi şu anda hazırlayamadık. Lütfen tekrar deneyin.",
    invalid_analysis_output: "İsteğinizi işlerken bir sorun oluştu. Lütfen tekrar deneyin.",
    execution_unavailable: "Yanıtı şu anda çalıştıramadık. Lütfen tekrar deneyin.",
    invalid_execution_output: "Kullanılabilir bir yanıt oluşturulamadı. Lütfen tekrar deneyin.",
    rate_limit_exceeded: "İstekler çok hızlı gönderiliyor.",
    usage_quota_exceeded: "Mevcut kullanım hakkınıza ulaştınız.",
    usage_accounting_failed: "Kullanım güvenli şekilde kaydedilemedi. Lütfen tekrar deneyin.",
    history_not_found: "Bu geçmiş kaydı bulunamadı.",
    document_empty: "Dosya boş. Lütfen içerik içeren bir belge seçin.",
    document_too_large: "Belge yükleme sınırını aşıyor.",
    document_unsupported_type: "Bu belge türü desteklenmiyor. PDF, DOCX, TXT veya Markdown seçin.",
    document_not_found: "Belge bulunamadı.",
    document_storage_failed: "Belge güvenli şekilde saklanamadı. Lütfen tekrar deneyin.",
    document_no_extractable_text: "Belgeden çıkarılabilir metin bulunamadı.",
    document_parse_failed: "Belge işlenemedi. Lütfen geçerli bir belge deneyin.",
    document_not_parsed: "Belge önce metin çıkarma işleminden geçirilmelidir.",
    document_chunking_failed: "Belge anlamlı parçalara ayrılamadı. Lütfen tekrar deneyin.",
    internal_error: "Beklenmeyen bir sorun oluştu. Lütfen tekrar deneyin.",
    default: "Bir şeyler ters gitti. Lütfen tekrar deneyin.",
  },
  en: {
    invalid_request: "Please check the information you entered.",
    analysis_unavailable: "We couldn’t prepare this request right now. Please try again.",
    invalid_analysis_output: "There was a problem processing your request. Please try again.",
    execution_unavailable: "We couldn’t run this right now. Please try again.",
    invalid_execution_output: "No usable answer was produced. Please try again.",
    rate_limit_exceeded: "Requests are being made too quickly.",
    usage_quota_exceeded: "You’ve reached your current usage allowance.",
    usage_accounting_failed: "Usage could not be recorded safely. Please try again.",
    history_not_found: "This history record could not be found.",
    document_empty: "The file is empty. Choose a document with content.",
    document_too_large: "The document exceeds the upload limit.",
    document_unsupported_type: "This document type is not supported. Choose PDF, DOCX, TXT, or Markdown.",
    document_not_found: "The document could not be found.",
    document_storage_failed: "The document could not be stored safely. Please try again.",
    document_no_extractable_text: "No extractable text was found in this document.",
    document_parse_failed: "The document could not be processed. Try a valid document.",
    document_not_parsed: "The document must be parsed before it can be chunked.",
    document_chunking_failed: "The document could not be split into chunks. Please try again.",
    internal_error: "Something unexpected happened. Please try again.",
    default: "Something went wrong. Please try again.",
  },
} as const;

export function localizedError(
  language: AppLanguage,
  code: string | null,
  details: ApiErrorDetails | null,
): string {
  const catalog = messages[language];
  const base = catalog[code as keyof typeof catalog] ?? catalog.default;
  if (code === "rate_limit_exceeded" && details?.retryAfterSeconds) {
    return `${base} ${language === "tr" ? `${details.retryAfterSeconds} saniye sonra tekrar deneyin.` : `Try again in ${details.retryAfterSeconds} seconds.`}`;
  }
  if (code === "usage_quota_exceeded" && details?.resetAt) {
    const reset = new Date(details.resetAt).toLocaleDateString(language === "tr" ? "tr-TR" : "en-US");
    return `${base} ${language === "tr" ? `Yenilenme: ${reset}.` : `Resets: ${reset}.`}`;
  }
  return base;
}
