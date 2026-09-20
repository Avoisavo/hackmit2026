// Shared presenter/face display. Effects are snapshots with IDs, never robot commands.
export function renderHare(root, demo) {
  if (!root) return;
  root.hidden = !demo;
  if (!demo) return;
  root.querySelector('[data-hare-equation]').textContent = demo.equation || demo.title;
  root.querySelector('[data-hare-source]').textContent = demo.evidence === 'presenter' ? 'Presenter fallback' : demo.evidence === 'camera' ? 'Camera count' : demo.motion === 'forward_jumps' ? 'Go2 forward jumps' : 'Screen hops';
  const effect = demo.effect;
  if (effect && root.dataset.effect !== effect.id) {
    root.dataset.effect = effect.id;
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
      const target = effect.kind === 'wobble' ? root.querySelector('.hare-ears') : root;
      target?.animate(effect.kind === 'wobble' ? [{transform:'rotate(0)'},{transform:'rotate(-15deg)'},{transform:'rotate(15deg)'},{transform:'rotate(0)'}] : [{transform:'translateY(0)'},{transform:'translateY(-32px)'},{transform:'translateY(0)'}], {duration:650});
    }
  }
  root.querySelector('[data-hare-hops]').textContent = demo.hops ? `${demo.hops} ${demo.motion === 'forward_jumps' ? 'jumps commanded' : 'screen hops'}` : '';
}
