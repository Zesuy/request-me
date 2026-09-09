export interface Source {
  title?: string;
  cwd?: string;
  host?: string;
}

export interface Choice {
  id: string;
  label: string;
  value: string;
}

export interface Message {
  id: string;
  thread_id: string;
  markdown: string;
  options?: Choice[];
  source: Source;
}

export interface Sent {
  id: string;
  status: string;
  message_id?: string;
}

export interface Answer {
  id: string;
  request_id: string;
  thread_id: string;
  text: string;
}

export interface Receipt {
  status: "accepted" | "failed" | "unknown" | "closed";
  detail?: string;
}
