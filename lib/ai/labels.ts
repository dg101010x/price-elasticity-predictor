export function modelLabel(modelId: string): string {
  const name = modelId.split(':')[0].split('/').pop() ?? modelId
  return name.replace(/-/g, ' ')
}
