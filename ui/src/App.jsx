import { useState, useEffect, useRef } from 'react'
import { useAuth } from './AuthContext'
import Login from './Login'
import './App.css'

function App() {
  const { user, loading, logout } = useAuth()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef(null)

  // Auto-scroll to the latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Reset messages and load history whenever the user changes (login/logout/switch)
  useEffect(() => {
    setMessages([])
    if (!user) return

    const loadHistory = async () => {
      try {
        const token = await user.getIdToken()
        const res = await fetch('/api/chat/history', {
          headers: { Authorization: `Bearer ${token}` },
        })
        const data = await res.json()
        if (data.history?.length) {
          setMessages(data.history)
        }
      } catch (err) {
        console.error('Failed to load chat history:', err)
      }
    }

    loadHistory()
  }, [user])

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || sending) return

    // Optimistically add the user message
    setMessages((prev) => [...prev, { role: 'user', text }])
    setInput('')
    setSending(true)

    try {
      const token = await user.getIdToken()
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: text }),
      })
      const data = await res.json()

      if (data.reply) {
        setMessages((prev) => [...prev, { role: 'model', text: data.reply }])
      } else if (data.error) {
        setMessages((prev) => [
          ...prev,
          { role: 'model', text: `Error: ${data.error}` },
        ])
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'model', text: 'Something went wrong. Please try again.' },
      ])
    } finally {
      setSending(false)
    }
  }

  const clearChat = async () => {
    try {
      const token = await user.getIdToken()
      await fetch('/api/chat/clear', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      setMessages([])
    } catch (err) {
      console.error('Failed to clear chat:', err)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  if (loading) {
    return (
      <div className="app">
        <h1>Loading...</h1>
      </div>
    )
  }

  if (!user) {
    return <Login />
  }

  return (
    <div className="app chat-layout">
      {/* Header */}
      <header className="app-header">
        <span className="header-title">AI Chat</span>
        <div className="header-actions">
          <span className="user-email">{user.email}</span>
          <button className="btn-header" onClick={clearChat}>
            Clear Chat
          </button>
          <button className="btn-header" onClick={logout}>
            Sign Out
          </button>
        </div>
      </header>

      {/* Messages area */}
      <main className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Send a message to start chatting!</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`chat-bubble ${msg.role}`}>
            <span className="chat-role">
              {msg.role === 'user' ? 'You' : 'AI'}
            </span>
            <div className="chat-text">{msg.text}</div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </main>

      {/* Input area */}
      <footer className="chat-input-bar">
        <textarea
          className="chat-input"
          rows={1}
          placeholder="Type a message..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={sending}
        />
        <button
          className="btn-send"
          onClick={sendMessage}
          disabled={sending || !input.trim()}
        >
          {sending ? '...' : 'Send'}
        </button>
      </footer>
    </div>
  )
}

export default App
