export const labels = {
  fr: {
    idle: 'Appuyez pour parler',
    recording: 'Écoute en cours...',
    processing: 'Réflexion...',
    speaking: 'Réponse en cours...',
    greeting: 'Bonjour ! Comment puis-je vous aider ?',
    hint: 'Posez votre question sur votre box, forfait ou connexion',
    placeholder: 'Ou tapez votre question ici...',
    send: 'Envoyer',
    endConversation: 'Terminer',
    connected: 'Connecté',
    disconnected: 'Déconnecté',
    error: 'Désolé, une erreur est survenue. Veuillez réessayer.',
  },
  en: {
    idle: 'Press to speak',
    recording: 'Listening...',
    processing: 'Thinking...',
    speaking: 'Speaking...',
    greeting: 'Hello! How can I help you?',
    hint: 'Ask about your router, plan, or connection',
    placeholder: 'Or type your question here...',
    send: 'Send',
    endConversation: 'End',
    connected: 'Connected',
    disconnected: 'Disconnected',
    error: 'Sorry, an error occurred. Please try again.',
  },
} as const

export type Language = keyof typeof labels
export type Labels = typeof labels[Language]

export function isLanguage(value: string): value is Language {
  return value in labels
}
