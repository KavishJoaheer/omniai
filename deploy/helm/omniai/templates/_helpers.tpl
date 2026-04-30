{{/*
Common helpers for the omniai chart.
*/}}

{{- define "omniai.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "omniai.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "omniai.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Common environment variables shared by api + worker pods.
*/}}
{{- define "omniai.commonEnv" -}}
- name: APP_ENV
  value: {{ .Values.config.appEnv | quote }}
- name: HTTP_PORT
  value: "9380"
- name: AUTO_CREATE_SCHEMA
  value: "false"
- name: DB_URL
  value: "postgresql+psycopg://{{ .Values.postgres.user }}:$(POSTGRES_PASSWORD)@{{ include "omniai.fullname" . }}-postgres:5432/{{ .Values.postgres.database }}"
- name: POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "omniai.fullname" . }}-secret
      key: postgresPassword
- name: REDIS_URL
  value: "redis://{{ include "omniai.fullname" . }}-redis:6379/0"
- name: OBJECT_STORE_KIND
  value: "s3"
- name: OBJECT_STORE_ENDPOINT
  value: "http://{{ include "omniai.fullname" . }}-minio:9000"
- name: OBJECT_STORE_REGION
  value: "us-east-1"
- name: OBJECT_STORE_ACCESS_KEY
  value: {{ .Values.minio.rootUser | quote }}
- name: OBJECT_STORE_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "omniai.fullname" . }}-secret
      key: minioPassword
- name: OBJECT_STORE_BUCKET
  value: {{ .Values.minio.bucket | quote }}
- name: SEARCH_KIND
  value: "opensearch"
- name: SEARCH_URL
  value: "http://{{ include "omniai.fullname" . }}-opensearch:9200"
- name: ENCRYPTION_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "omniai.fullname" . }}-secret
      key: encryptionKey
- name: AUTH_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ include "omniai.fullname" . }}-secret
      key: authSecret
- name: BOOTSTRAP_ADMIN_EMAIL
  value: {{ .Values.config.bootstrapAdminEmail | quote }}
- name: BOOTSTRAP_ADMIN_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "omniai.fullname" . }}-secret
      key: bootstrapAdminPassword
- name: RATE_LIMIT_PER_MINUTE
  value: {{ .Values.config.rateLimitPerMinute | quote }}
- name: TENANT_MAX_DOCUMENTS
  value: {{ .Values.config.tenantMaxDocuments | quote }}
- name: TENANT_MAX_STORAGE_BYTES
  value: {{ .Values.config.tenantMaxStorageBytes | quote }}
- name: RERANKER_KIND
  value: {{ .Values.config.rerankerKind | quote }}
- name: RERANKER_MODEL
  value: {{ .Values.config.rerankerModel | quote }}
- name: OCR_KIND
  value: {{ .Values.config.ocrKind | quote }}
- name: OLLAMA_BASE_URL
  value: {{ .Values.config.ollamaBaseUrl | quote }}
- name: OLLAMA_VISION_MODEL
  value: {{ .Values.config.ollamaVisionModel | quote }}
{{- end -}}
