# Urbix Vision: O Report Indispensável para Desenvolvimento Imobiliário

## O que temos hoje (MVP)
1. Site Information (lot/plan, area, tenure)
2. Planning Zone + mapa com legenda
3. Overlays (flood, acid sulfate, heritage, etc)
4. Infrastructure (water, sewer, stormwater network)
5. Contours & Elevation (QLD LiDAR)
6. Buildability (height, setbacks, GFA, uses, subdivision potential)
7. Transport Hierarchy

---

## Dados de DA Disponíveis (SCC API)

**Endpoint:** `geopublic.scc.qld.gov.au/arcgis/rest/services/PlanningCadastre/Applications_SCRC/MapServer`

| Layer | Dados |
|-------|-------|
| 0 | Development Applications — In Progress |
| 1 | Development Applications — Decided/Past |
| 2 | Building Applications — In Progress |
| 3 | Building Applications — Decided/Past |
| 4 | Plumbing Applications — In Progress |
| 5 | Plumbing Applications — Decided/Past |
| 6 | Approvals varying Planning Scheme |

**Campos:** ram_id, description, category_desc, decision, progress, assessment_level (Code/Impact), d_date_rec, d_decision_made, land_parcel_relationship

**Portal de detalhe:** `developmenti.sunshinecoast.qld.gov.au/Home/FilterDirect?LotPlan={lot}/{plan}`

---

## O que falta para ser 100x mais útil

### 🏗️ Tier 1 — Dados que já podemos puxar (APIs existentes)

#### 1. Development Application History (DA)
- DAs aprovadas/recusadas NO lote (precedente direto)
- DAs aprovadas/recusadas NEARBY (500m radius — precedente por vizinhança)
- Timeline visual de DAs
- Link para documentos no portal DevelopmentI
- **Valor:** Developer sabe EXATAMENTE o que já foi tentado e o que council aceita

#### 2. Neighbouring Properties Analysis
- Mapa mostrando lotes vizinhos com suas zonas e DAs recentes
- Usos existentes ao redor (residencial, comercial, industrial)
- Alturas aprovadas nearby → indica o que council aceita na prática
- **Valor:** Contexto real de mercado e aceitação política

#### 3. Flood Modelling Detail
- Não só "está em flood overlay" mas QUAL nível de flood (Q100, Q50, Q20)
- Freeboard requirements
- Minimum habitable floor level
- **Valor:** Determina se é viável construir e a que custo

#### 4. Environmental Constraints Deep Dive
- Koala habitat priority areas
- Vegetation Management Act triggers
- Acid sulfate soil investigation requirements
- Waterway buffer distances
- **Valor:** Custos ocultos de environmental compliance

#### 5. Easements & Covenants
- SCC ParcelInformation_SCRC tem Easements (Layer 1) e Covenants (Layer 0)
- Impactam onde se pode construir dentro do lote
- **Valor:** Evita surpresas no design

### 📊 Tier 2 — Análise Inteligente (AI-powered)

#### 6. Development Feasibility Summary
- Max GFA calculado (zona + height + setbacks + site cover)
- Estimativa de yield (unidades/lotes)
- Development charges estimados (infrastructure contributions)
- Resumo: "Este lote pode render X unidades de Y m² cada"
- **Valor:** First-cut feasibility antes de gastar $ com consultores

#### 7. Planning Assessment Pathway
- Qual assessment track (Code, Impact, Prohibited)?
- Triggers de assessment (which codes apply?)
- Expected timeline (Code: 25 business days, Impact: 30-50 business days)
- Estimated application fees
- Checklist de documentos necessários
- **Valor:** Developer sabe EXATAMENTE o caminho e quanto custa/demora

#### 8. Precedent Intelligence (AI)
- Análise das DAs approved nearby nos últimos 5 anos
- Padrões: "Council consistentemente aprova 6+ storeys nesta área"
- DAs recusadas → razões comuns (traffic, amenity, character)
- Score de risco político
- **Valor:** Prediz chances de aprovação antes de investir

#### 9. Site Constraints Score
- Score 1-100 de "facilidade de desenvolvimento"
- Penalidades: flood, slope, acid sulfate, heritage, koala, easements
- Bonuses: flat, all infrastructure, good zone, precedent approvals
- **Valor:** Quick triage — developer olha score e decide se vale a pena

### 🚀 Tier 3 — Diferenciação Radical

#### 10. AI Planning Advisor
- Chat: "Posso fazer um hotel de 10 andares aqui?"
- Responde baseado em zone, overlays, height limits, precedent DAs
- Sugere estratégias: "Consider code assessment with MCU if under X units"
- **Valor:** Town planner virtual 24/7

#### 11. Market Context
- Sales data de propriedades similares nearby (RP Data API)
- Median prices by suburb
- Development trends (mais units ou casas?)
- **Valor:** Contexto de mercado para feasibility

#### 12. 3D Buildable Envelope
- Visualização 3D do que se pode construir (height + setbacks)
- Overlay com terreno real
- Solar access analysis
- **Valor:** Architect pode ver a "caixa" antes de desenhar

---

## Públicos-alvo e o que cada um precisa

| Público | Dados Essenciais | Disposição a Pagar |
|---------|------------------|-------------------|
| **Property Developer** | Zone, DA history, feasibility, yield, precedent | $$$$ (A$50-200/report) |
| **Town Planner** | All technical data, assessment pathway, codes | $$$ (A$30-100/report) |
| **Architect** | Setbacks, height, envelope, contours, easements | $$ (A$20-50/report) |
| **Surveyor** | Boundaries, easements, contours, infrastructure | $$ (A$20-50/report) |
| **Real Estate Investor** | Zone, DA precedent, feasibility, market data | $$$ (A$30-100/report) |
| **Lawyer (Due Diligence)** | Covenants, easements, DAs, constraints | $$$ (A$30-100/report) |
| **Home Buyer** | Simplified overlays, flood risk, neighbors | $ (A$10-20/report) |
| **Bank/Mortgage** | Risk assessment, constraints, feasibility | $$$ (bulk pricing) |

---

## Roadmap Sugerido

### Fase 1: DA Integration (Esta semana)
- [ ] Adicionar seção "Development History" ao report
- [ ] DAs no lote + DAs nearby (500m)
- [ ] Timeline visual
- [ ] Links para DevelopmentI portal

### Fase 2: Deep Constraints (Próxima semana)
- [ ] Easements & Covenants do lote
- [ ] Flood detail levels
- [ ] Environmental constraints detail
- [ ] Neighbouring properties map

### Fase 3: Intelligence Layer (Mês 1)
- [ ] Feasibility calculator (yield, GFA)
- [ ] Assessment pathway guide
- [ ] Precedent analysis (DAs approved nearby)
- [ ] Site constraints score (1-100)

### Fase 4: Premium Features (Mês 2-3)
- [ ] AI Planning Advisor (chat)
- [ ] 3D buildable envelope
- [ ] Market context integration
- [ ] PDF export com branding profissional

---

## Competição e Diferenciação

| Concorrente | O que faz | Onde Urbix ganha |
|-------------|-----------|------------------|
| Nearmap (PropTech) | Aerial imagery + AI detection | Nós: planning intelligence, não só imagens |
| Archistar | Feasibility + envelope | Nós: SCC-specific, 10x mais profundo em local data |
| Cordell | Building cost data | Nós: upstream — antes do design, na fase de viabilidade |
| Council DA portals | Raw data, hard to use | Nós: curated, analyzed, actionable |
| Town planners (human) | Expert opinion, expensive | Nós: instant, 1/10 do custo, available 24/7 |

**Moat:** Ninguém combina dados de planning + infrastructure + DA history + AI analysis num único report instantâneo para Sunshine Coast. E o SCC tem dados EXCEPCIONALMENTE ricos via ArcGIS.

---

## Para Treinar o Sistema com DA Data

### Estratégia de Coleta
1. **Bulk download** todas as DAs decided (Layer 1) — ~thousands of records
2. **Classificar** por tipo: MCU (material change of use), ROL (reconfiguration of lot), OPW (operational works)
3. **Correlacionar** com zona + overlays → "que tipo de DA é approved em que zona?"
4. **Treinar modelo** de predição: dado zona + overlays + constraints → probabilidade de aprovação para tipo X

### Campos Úteis para ML
- `category_desc` → tipo de application
- `assessment_level` → Code vs Impact
- `decision` → Approved/Refused/Lapsed
- Zone do lote → correlação zone ↔ decision
- Overlays ativos → impacto em approvals
- `description` → NLP para extrair tipo de desenvolvimento

### Volume Estimado
- SCC processa ~3,000-5,000 DAs/ano
- Histórico disponível desde ~2000 → potencialmente 50k+ records
- Suficiente para patterns significativos

---

*"O objetivo não é substituir o town planner. É dar a quem precisa 80% da informação em 10 segundos, para que o town planner foque nos 20% que realmente precisam de expertise humana."*
