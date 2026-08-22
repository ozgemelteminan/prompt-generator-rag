# Retrieval evaluation v1 review

Static manual-review index. Ground truth is source-block based; excerpts point reviewers to the original block files.

## Short source excerpts

| Block | Short excerpt |
| --- | --- |
| tr-rrf-1 | "yoğun ve seyrek arama listelerini ... sıra bilgisiyle birleştirir" |
| tr-rrf-2 | "farklı skor ölçeklerinin ... karşılaştırılması sorununu azaltır" |
| tr-rrf-4 | "Retriever geri çağırmayı ... reranker ... kesinliği artırır" |
| tr-rrf-5 | "yinelenen adaylar tekilleştirilmeli" |
| tr-sec-1 | "belgeler güvenilmeyen veridir" |
| tr-sec-2 | "kod bloklarını, makroları, PDF JavaScript'ini ... çalıştırmaz" |
| tr-sec-4 | "kullanıcı, çalışma alanı ve belge kimliği filtreleri" |
| tr-sec-5 | "kritik bir veri sızıntısıdır" |
| tr-morph-1 | "bölümü, başlığı ve paragrafı korur" |
| tr-morph-2 | "belirteç sınırı son başvuru noktasıdır" |
| tr-morph-4 | "bağlam sürekliliğini korur" |
| tr-morph-5 | "kaynak blok aralığı ... saklanır" |
| en-ret-1 | "retriever optimizes recall ... reranker optimizes precision" |
| en-ret-2 | "raw scores ... are not compatible" |
| en-ret-4 | "deduplicates candidates ... preserves citation metadata" |
| en-ret-5 | "say so instead of inventing" |
| en-code-1 | "deterministic pipeline is preferred" |
| en-code-2 | "return text.replace" |
| en-code-4 | "invalid input, stable output, and source-order" |
| en-code-5 | "Do not execute code" |
| en-plan-1 | "Inspect only relevant files" |
| en-plan-2 | "services own use-case orchestration" |
| en-plan-4 | "focused unit tests ... integration checks" |
| en-plan-5 | "must not claim unimplemented features work" |

| Query | Language | Category | Required blocks | Relevant excerpt references |
| --- | --- | --- | --- | --- |
| RRF nedir? | tr | factual | tr-rrf-1 | `tr-rrf-1` |
| Skor ölçekleri neden karışmaz? | tr | paraphrase | tr-rrf-2 | `tr-rrf-2` |
| Sıra bilgisiyle birleştirme nasıl çalışır? | tr | hard_paraphrase | tr-rrf-1 | `tr-rrf-1` |
| Yoğun ve seyrek arama terimleri neyi anlatır? | tr | terminology_mismatch | tr-rrf-2 | `tr-rrf-2` |
| Birleştirilmiş adaylar nasıl tekilleştirilir? | tr | morphology_heavy | tr-rrf-4 | `tr-rrf-4` |
| Kullanım Notu ne söyler? | tr | heading_dependent | tr-rrf-3, tr-rrf-4 | `tr-rrf-3`; `tr-rrf-4` |
| Ham skor ve sıra bilgisi ilişkisi nedir? | tr | cross_paragraph | tr-rrf-1, tr-rrf-2 | `tr-rrf-1`; `tr-rrf-2` |
| RRF başka hangi sorunla karıştırılmamalıdır? | tr | near_negative | tr-rrf-2 | `tr-rrf-2` |
| Retriever ile reranker arasındaki fark nedir? | tr | same_topic_competitor | tr-rrf-4 | `tr-rrf-4` |
| RRF ve kaynak metaverisi nasıl birlikte kullanılır? | tr | multi_section | tr-rrf-1, tr-rrf-5 | `tr-rrf-1`; `tr-rrf-5` |
| Üst sıralar nasıl ödüllendirilir? | tr | factual | tr-rrf-1 | `tr-rrf-1` |
| Kesinlik hangi aşamada artar? | tr | paraphrase | tr-rrf-5 | `tr-rrf-5` |
| Yinelenen adaylar ne olur? | tr | hard_paraphrase | tr-rrf-4 | `tr-rrf-4` |
| Birleştirme sonrası hangi bilgi korunur? | tr | factual | tr-rrf-5 | `tr-rrf-5` |
| Belge talimatları güvenilir mi? | tr | factual | tr-sec-1 | `tr-sec-1` |
| Ayrıştırıcı neleri çalıştırmaz? | tr | paraphrase | tr-sec-2 | `tr-sec-2` |
| Güvenilmeyen veri nasıl ele alınır? | tr | hard_paraphrase | tr-sec-1 | `tr-sec-1` |
| Sahiplik filtresi ne demektir? | tr | terminology_mismatch | tr-sec-2 | `tr-sec-2` |
| Çalışma alanı sızıntısı nasıl önlenir? | tr | morphology_heavy | tr-sec-4 | `tr-sec-4` |
| Sahiplik başlığı ne içerir? | tr | heading_dependent | tr-sec-3, tr-sec-4 | `tr-sec-3`; `tr-sec-4` |
| Talimat yetkisi ve erişim filtresi nasıl ilişkilidir? | tr | cross_paragraph | tr-sec-1, tr-sec-2 | `tr-sec-1`; `tr-sec-2` |
| PDF JavaScript ile makro aynı şey midir? | tr | near_negative | tr-sec-2 | `tr-sec-2` |
| Kullanıcı ve çalışma alanı filtresi farkı nedir? | tr | same_topic_competitor | tr-sec-4 | `tr-sec-4` |
| Belge güvenliği ile sahiplik birlikte nasıl çalışır? | tr | multi_section | tr-sec-1, tr-sec-5 | `tr-sec-1`; `tr-sec-5` |
| Dış bağlantılar neden yüklenmez? | tr | factual | tr-sec-1 | `tr-sec-1` |
| Kritik veri sızıntısı nedir? | tr | paraphrase | tr-sec-5 | `tr-sec-5` |
| Belge kimliği neden gerekir? | tr | hard_paraphrase | tr-sec-4 | `tr-sec-4` |
| Başka alan parçaları görünür mü? | tr | factual | tr-sec-5 | `tr-sec-5` |
| Yapı farkındalıklı parçalama nedir? | tr | factual | tr-morph-1 | `tr-morph-1` |
| Uzun paragraf nasıl bölünür? | tr | paraphrase | tr-morph-2 | `tr-morph-2` |
| Belirteç sınırı ne zaman kullanılır? | tr | hard_paraphrase | tr-morph-1 | `tr-morph-1` |
| Anlamsal sınır terimi ne demektir? | tr | terminology_mismatch | tr-morph-2 | `tr-morph-2` |
| Parçalanmış belgelerde hangi aralık saklanır? | tr | morphology_heavy | tr-morph-4 | `tr-morph-4` |
| Örtüşme başlığı ne açıklar? | tr | heading_dependent | tr-morph-3, tr-morph-4 | `tr-morph-3`; `tr-morph-4` |
| Paragraf ve belirteç sırası nedir? | tr | cross_paragraph | tr-morph-1, tr-morph-2 | `tr-morph-1`; `tr-morph-2` |
| Rastgele pencere ile semantik sınır aynı mıdır? | tr | near_negative | tr-morph-2 | `tr-morph-2` |
| Örtüşme bağlamı nasıl korur? | tr | same_topic_competitor | tr-morph-4 | `tr-morph-4` |
| Bölüm sınırı ve denetim bilgisi nasıl birlikte çalışır? | tr | multi_section | tr-morph-1, tr-morph-5 | `tr-morph-1`; `tr-morph-5` |
| Cümle sınırı neden tercih edilir? | tr | factual | tr-morph-1 | `tr-morph-1` |
| İlgisiz bölümler birleşir mi? | tr | paraphrase | tr-morph-5 | `tr-morph-5` |
| Kaynak blok aralığı ne işe yarar? | tr | hard_paraphrase | tr-morph-4 | `tr-morph-4` |
| Örtüşen parçalarda ne korunur? | tr | factual | tr-morph-5 | `tr-morph-5` |
| What does a retriever optimize? | en | factual | en-ret-1 | `en-ret-1` |
| Why are raw dense and sparse scores incompatible? | en | paraphrase | en-ret-2 | `en-ret-2` |
| How are score scales combined safely? | en | hard_paraphrase | en-ret-1 | `en-ret-1` |
| What does context building mean? | en | terminology_mismatch | en-ret-2 | `en-ret-2` |
| Which metadata survives context selection? | en | morphology_heavy | en-ret-4 | `en-ret-4` |
| What does the Context Building heading cover? | en | heading_dependent | en-ret-3, en-ret-4 | `en-ret-3`; `en-ret-4` |
| How do recall and citation preservation relate? | en | cross_paragraph | en-ret-1, en-ret-2 | `en-ret-1`; `en-ret-2` |
| Is a context builder the same as a reranker? | en | near_negative | en-ret-2 | `en-ret-2` |
| What is the difference between retriever and reranker? | en | same_topic_competitor | en-ret-4 | `en-ret-4` |
| How should weak evidence be handled across sections? | en | multi_section | en-ret-1, en-ret-5 | `en-ret-1`; `en-ret-5` |
| Why reduce overlap? | en | factual | en-ret-1 | `en-ret-1` |
| What does insufficient evidence require? | en | paraphrase | en-ret-5 | `en-ret-5` |
| Which stage deduplicates candidates? | en | hard_paraphrase | en-ret-4 | `en-ret-4` |
| What avoids invented document claims? | en | factual | en-ret-5 | `en-ret-5` |
| When is deterministic processing preferred? | en | factual | en-code-1 | `en-code-1` |
| What does normalize change? | en | paraphrase | en-code-2 | `en-code-2` |
| How are line endings normalized? | en | hard_paraphrase | en-code-1 | `en-code-1` |
| What does the Tests heading require? | en | terminology_mismatch | en-code-2 | `en-code-2` |
| Which code must remain unexecuted? | en | morphology_heavy | en-code-4 | `en-code-4` |
| What belongs in the Tests section? | en | heading_dependent | en-code-3, en-code-4 | `en-code-3`; `en-code-4` |
| How do stable output and source order relate? | en | cross_paragraph | en-code-1, en-code-2 | `en-code-1`; `en-code-2` |
| Is uploaded code executed for parsing? | en | near_negative | en-code-2 | `en-code-2` |
| What is source-order preservation? | en | same_topic_competitor | en-code-4 | `en-code-4` |
| How do tests and code safety work together? | en | multi_section | en-code-1, en-code-5 | `en-code-1`; `en-code-5` |
| What does deterministic mean here? | en | factual | en-code-1 | `en-code-1` |
| Which invalid inputs need coverage? | en | paraphrase | en-code-5 | `en-code-5` |
| Can document code run? | en | hard_paraphrase | en-code-4 | `en-code-4` |
| Why keep tests stable? | en | factual | en-code-5 | `en-code-5` |
| What should be inspected before a change? | en | factual | en-plan-1 | `en-plan-1` |
| Which layer owns orchestration? | en | paraphrase | en-plan-2 | `en-plan-2` |
| What do route handlers do? | en | hard_paraphrase | en-plan-1 | `en-plan-1` |
| What does the Verification heading contain? | en | terminology_mismatch | en-plan-2 | `en-plan-2` |
| When should documentation be updated? | en | morphology_heavy | en-plan-4 | `en-plan-4` |
| What belongs under Verification? | en | heading_dependent | en-plan-3, en-plan-4 | `en-plan-3`; `en-plan-4` |
| How do focused tests and documentation claims relate? | en | cross_paragraph | en-plan-1, en-plan-2 | `en-plan-1`; `en-plan-2` |
| Are repositories responsible for orchestration? | en | near_negative | en-plan-2 | `en-plan-2` |
| How do services differ from routes? | en | same_topic_competitor | en-plan-4 | `en-plan-4` |
| How do planning and verification span sections? | en | multi_section | en-plan-1, en-plan-5 | `en-plan-1`; `en-plan-5` |
| What is a smallest coherent change? | en | factual | en-plan-1 | `en-plan-1` |
| Which checks follow unit tests? | en | paraphrase | en-plan-5 | `en-plan-5` |
| Should unimplemented features be claimed? | en | hard_paraphrase | en-plan-4 | `en-plan-4` |
| What does a repository own? | en | factual | en-plan-5 | `en-plan-5` |

Review source text in `evals/datasets/documents/`; no generated chunk ID is used as a label.
