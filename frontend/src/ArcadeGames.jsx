import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Gamepad2, Heart, RotateCcw, Send } from 'lucide-react'
import { api } from './api'

const games = [
  ['tic_tac_toe', 'Tic-Tac-Toe', '✕', 'Claim three squares in a row.'],
  ['connect_four', 'Connect Four', '●', 'Drop discs and make a line of four.'],
  ['rock_paper_scissors', 'Rock Paper Scissors', '✊', 'Choose in secret, then reveal together.'],
  ['emoji_match', 'Emoji Match', '✨', 'Take turns finding matching pairs.'],
  ['number_hunt', 'Number Hunt', '🔎', 'Guess the hidden number from 1 to 20.'],
  ['word_duel', 'Word Duel', '🔤', 'Reveal the friendship word one letter at a time.'],
  ['math_duel', 'Math Duel', '➕', 'Six quick mental-math rounds.'],
  ['higher_lower', 'Higher or Lower', '🃏', 'Predict whether the next card is higher.'],
  ['would_you_rather', 'Would You Rather', '💭', 'Vote, then see if you match.'],
  ['friendship_trivia', 'Friendship Trivia', '🧠', 'Answer six playful BondBook questions.'],
]

function Result({ game }) {
  if (game.status !== 'finished') return <b>{game.is_my_turn || ['rock_paper_scissors', 'would_you_rather'].includes(game.game_type) ? 'Your move' : 'Waiting for your friend'}</b>
  if (!game.winner_id) return <b>{game.game_type === 'would_you_rather' ? 'Votes revealed!' : 'It is a draw.'}</b>
  return <b>{game.is_winner ? 'You won!' : 'Your friend won!'}</b>
}

function AnswerBox({ label, submit, disabled, numeric = false, maxLength = 20 }) {
  const [value, setValue] = useState('')
  const send = event => { event.preventDefault(); if (!value.trim()) return; submit({ choice: value.trim() }); setValue('') }
  return <form className="arcade-answer" onSubmit={send}><input type={numeric ? 'number' : 'text'} min={numeric ? '1' : undefined} max={numeric ? '20' : undefined} maxLength={maxLength} value={value} onChange={event => setValue(event.target.value)} placeholder={label} disabled={disabled}/><button className="button primary" disabled={disabled || !value.trim()}><Send size={16}/> Send</button></form>
}

function GamePlay({ game, onMove, busy }) {
  const canAct = game.status === 'active' && (game.is_my_turn || ['rock_paper_scissors', 'would_you_rather'].includes(game.game_type))
  const move = (body) => onMove(body)
  if (game.game_type === 'tic_tac_toe') return <div className="arcade-board three-board">{game.board.split('').map((cell, index) => <button key={index} onClick={() => move({ position: index })} disabled={!canAct || busy || cell !== '-'}>{cell === '-' ? '' : cell}</button>)}</div>
  if (game.game_type === 'connect_four') return <><div className="connect-controls">{Array.from({ length: 7 }, (_, column) => <button key={column} className="button secondary" onClick={() => move({ position: column })} disabled={!canAct || busy}>↓</button>)}</div><div className="connect-board">{game.board.split('').map((cell, index) => <span key={index} className={cell === '-' ? '' : cell.toLowerCase()}>{cell === '-' ? '' : cell}</span>)}</div></>
  if (game.game_type === 'rock_paper_scissors') return <div className="choice-row">{[['rock','✊'],['paper','✋'],['scissors','✌️']].map(([choice, icon]) => <button key={choice} onClick={() => move({ choice })} disabled={!canAct || busy || Boolean(game.my_choice)}>{icon}<span>{choice}</span></button>)}<small>{game.my_choice ? 'Your choice is locked. Waiting for your friend.' : game.opponent_ready ? 'Your friend is ready — choose now.' : 'Pick privately. Your friend cannot see it yet.'}</small></div>
  if (game.game_type === 'emoji_match') return <div className="emoji-board">{game.display.map((emoji, index) => <button key={index} onClick={() => move({ position: index })} disabled={!canAct || busy || emoji !== '?'}>{emoji}</button>)}</div>
  if (game.game_type === 'number_hunt') return <><p className="game-helper">Take turns guessing the number from 1 to 20. {game.remaining} guesses remain.</p><AnswerBox label="Number 1–20" numeric submit={move} disabled={!canAct || busy}/>{game.guesses?.length > 0 && <div className="guess-list">{game.guesses.map((guess, index) => <span key={index}>Guess {guess.value}</span>)}</div>}</>
  if (game.game_type === 'word_duel') return <><p className="word-mask">{game.word}</p><p className="game-helper">Wrong letters: {game.misses}/6 · Used: {game.guessed?.join(', ') || 'none'}</p><AnswerBox label="One letter" maxLength={1} submit={move} disabled={!canAct || busy}/>{game.answer && <p className="game-helper">The word was {game.answer}.</p>}</>
  if (game.game_type === 'math_duel') return <><p className="math-question">{game.question} = ?</p><p className="game-helper">Round {game.round + 1} of 6</p><AnswerBox label="Your answer" numeric submit={move} disabled={!canAct || busy}/></>
  if (game.game_type === 'higher_lower') return <><p className="card-number">{game.current}</p><p className="game-helper">Will the next card be higher or lower?</p><div className="choice-row two"><button onClick={() => move({ choice: 'higher' })} disabled={!canAct || busy}>↑ Higher</button><button onClick={() => move({ choice: 'lower' })} disabled={!canAct || busy}>↓ Lower</button></div></>
  if (game.game_type === 'would_you_rather') return <><p className="wyr-prompt">{game.prompt}</p><div className="choice-row two"><button onClick={() => move({ choice: 'A' })} disabled={!canAct || busy || Boolean(game.my_vote)}>A · {game.options[0]}</button><button onClick={() => move({ choice: 'B' })} disabled={!canAct || busy || Boolean(game.my_vote)}>B · {game.options[1]}</button></div><p className="game-helper">{game.my_vote ? 'Your vote is in. Waiting for your friend.' : 'Choose your favourite.'}</p></>
  if (game.game_type === 'friendship_trivia') return <><p className="wyr-prompt">{game.question}</p><div className="trivia-options">{game.options.map((option, index) => <button key={option} onClick={() => move({ choice: String(index) })} disabled={!canAct || busy}>{String.fromCharCode(65 + index)} · {option}</button>)}</div><p className="game-helper">Question {game.round + 1} of 6</p></>
  return null
}

export default function ArcadeGames({ user, show }) {
  const [selected, setSelected] = useState('tic_tac_toe'); const [data, setData] = useState(null); const [busy, setBusy] = useState(false)
  const load = useCallback(() => api(`/api/games/${selected}`).then(setData).catch(error => setData({ error: error.message })), [selected])
  useEffect(() => { load(); const timer = window.setInterval(load, 5000); return () => window.clearInterval(timer) }, [load])
  const start = async () => { setBusy(true); try { setData(await api(`/api/games/${selected}`, { method: 'POST' })); show('Game started — your friend has been notified.') } catch (error) { show(error.message, 'error') } finally { setBusy(false) } }
  const move = async body => { if (!data?.game || busy) return; setBusy(true); try { setData(await api(`/api/games/${selected}/${data.game.id}/move`, { method: 'POST', body: JSON.stringify(body) })) } catch (error) { show(error.message, 'error') } finally { setBusy(false) } }
  const details = games.find(([type]) => type === selected)
  if (!user.friend) return <div className="page arcade-page"><p className="eyebrow">Play together</p><h1>Duo arcade</h1><div className="empty"><div className="empty-icon"><Gamepad2/></div><h3>Connect your friend first</h3><p>All 10 games are private to one connected pair.</p><Link className="button primary" to="/settings">Connect friend</Link></div></div>
  return <div className="page arcade-page"><section className="arcade-head"><div><p className="eyebrow">Play together</p><h1>Duo arcade</h1><p>Ten private games for you and {user.friend.name}. The board refreshes automatically.</p></div><span className="arcade-count"><Gamepad2/> 10 games</span></section><div className="game-library">{games.map(([type, title, icon, description]) => <button key={type} onClick={() => setSelected(type)} className={selected === type ? 'selected' : ''}><span>{icon}</span><b>{title}</b><small>{description}</small></button>)}</div><section className="arcade-game"><div className="arcade-game-title"><div><span>{details[2]}</span><h2>{details[1]}</h2><p>{details[3]}</p></div>{data?.game && <Result game={data.game}/>}</div>{!data ? <div className="page-loading">Loading game…</div> : data.error ? <div className="notice error">{data.error}</div> : !data.game ? <div className="arcade-start"><Heart/><p>Ready for a new round with {user.friend.name}?</p><button className="button primary" onClick={start} disabled={busy}>Start game</button></div> : <><GamePlay game={data.game} onMove={move} busy={busy}/>{data.game.status === 'finished' && <button className="button secondary arcade-restart" onClick={start} disabled={busy}><RotateCcw size={16}/> Play again</button>}</>}</section></div>
}
