const CONFETTI_COLORS = ['--ink-amber-5', '--ink-blue-5', '--ink-green-5', '--ink-pink-5', '--ink-violet-5']

export function burstConfetti(canvas, { pieces = 90, durationMs = 1200 } = {}) {
  const context = canvas?.getContext('2d')
  if (!context) return
  const style = getComputedStyle(canvas)
  const colors = CONFETTI_COLORS.map((name) => style.getPropertyValue(name).trim())
  const { width, height } = canvas.getBoundingClientRect()
  const ratio = window.devicePixelRatio || 1
  canvas.width = width * ratio
  canvas.height = height * ratio
  context.scale(ratio, ratio)
  const confetti = Array.from({ length: pieces }, (_, index) => ({
    x: width / 2,
    y: height * 0.6,
    velocityX: (Math.random() - 0.5) * 9,
    velocityY: -3 - Math.random() * 6,
    rotation: Math.random() * Math.PI,
    spin: (Math.random() - 0.5) * 0.4,
    size: 4 + Math.random() * 4,
    color: colors[index % colors.length],
  }))
  const startedAt = performance.now()

  function draw(now) {
    const elapsed = now - startedAt
    context.clearRect(0, 0, width, height)
    if (elapsed > durationMs) return
    context.globalAlpha = 1 - elapsed / durationMs
    for (const piece of confetti) {
      piece.velocityY += 0.25
      piece.x += piece.velocityX
      piece.y += piece.velocityY
      piece.rotation += piece.spin
      context.save()
      context.translate(piece.x, piece.y)
      context.rotate(piece.rotation)
      context.fillStyle = piece.color
      context.fillRect(-piece.size / 2, -piece.size / 4, piece.size, piece.size / 2)
      context.restore()
    }
    requestAnimationFrame(draw)
  }
  requestAnimationFrame(draw)
}
