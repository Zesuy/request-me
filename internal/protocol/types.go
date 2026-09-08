package protocol

type Source struct {
	Title string `json:"title,omitempty"`
	CWD   string `json:"cwd,omitempty"`
	Host  string `json:"host,omitempty"`
}

type Option struct {
	ID    string `json:"id"`
	Label string `json:"label"`
	Value string `json:"value"`
}

type Message struct {
	ID       string   `json:"id"`
	ThreadID string   `json:"thread_id"`
	Markdown string   `json:"markdown"`
	Options  []Option `json:"options,omitempty"`
	Source   Source   `json:"source"`
}

type Sent struct {
	ID        string `json:"id"`
	Status    string `json:"status"`
	MessageID string `json:"message_id,omitempty"`
}

type Answer struct {
	ID        string `json:"id"`
	RequestID string `json:"request_id"`
	ThreadID  string `json:"thread_id"`
	Text      string `json:"text"`
}

type Receipt struct {
	Status string `json:"status"`
	Detail string `json:"detail,omitempty"`
}
