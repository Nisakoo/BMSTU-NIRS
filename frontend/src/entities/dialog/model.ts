export interface DialogSummary {
  dialogId: string;
  title: string | null;
  updatedAt: string;
}

export interface DialogMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  feedback: number | null;
  report: 'sent' | 'reviewed' | null;
  audioVoices: string[];
}

export interface ReportNewsItem {
  reportId: number;
  dialogId: string | null;
  dialogTitle: string | null;
}

export type DialogEventType = 'ready' | 'message_start' | 'message_delta' | 'message_end' | 'message_error';
