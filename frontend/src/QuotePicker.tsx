import React, { useState } from "react";
import { Modal, ScrollView, Text, TouchableOpacity, View } from "react-native";
import { COLORS } from "./theme";

type Props = { paragraph: string; onClose: () => void; onSave: (quote?: string, occurrence?: number) => void };

export default function QuotePicker({ paragraph, onClose, onSave }: Props) {
  const words = Array.from(paragraph.matchAll(/\S+/g));
  const [first, setFirst] = useState<number | null>(null);
  const [last, setLast] = useState<number | null>(null);
  const left = first === null ? 0 : Math.min(first, last ?? first);
  const right = first === null ? words.length - 1 : Math.max(first, last ?? first);
  const start = words[left]?.index ?? 0;
  const end = (words[right]?.index ?? 0) + (words[right]?.[0].length ?? 0);
  const quote = first === null ? paragraph : paragraph.slice(start, end);
  let occurrence = 0;
  if (first !== null && quote) {
    for (let at = paragraph.indexOf(quote); at >= 0 && at < start; at = paragraph.indexOf(quote, at + 1)) occurrence++;
  }
  const tooLong = Array.from(quote).length > 600;
  function pick(index: number) {
    if (first === null || last !== null) { setFirst(index); setLast(null); }
    else setLast(index);
  }
  return <Modal transparent animationType="fade" onRequestClose={onClose}>
    <View style={{ flex: 1, justifyContent: "center", padding: 24, backgroundColor: "#000a" }}>
      <View style={{ backgroundColor: COLORS.surfaceDeep, padding: 18, maxHeight: "85%", gap: 14 }}>
        <Text style={{ color: COLORS.textPrimary }}>Pin a passage</Text>
        <Text style={{ color: COLORS.textSecondary }}>Tap the first and last words to mark a quote.</Text>
        <ScrollView><Text style={{ color: COLORS.textPrimary, lineHeight: 28 }}>{words.map((word, i) =>
          <React.Fragment key={word.index}>{paragraph.slice(i ? words[i-1].index! + words[i-1][0].length : 0, word.index)}
            <Text onPress={() => pick(i)} style={first !== null && i >= left && i <= right ? { color: COLORS.primary, textDecorationLine: "underline" } : undefined}>{word[0]}</Text>
          </React.Fragment>)}</Text></ScrollView>
        {tooLong || occurrence > 50 ? <Text style={{ color: COLORS.textSecondary }}>{tooLong ? "Choose a shorter passage (600 characters maximum)." : "Include a nearby word to distinguish this occurrence."}</Text> : null}
        <TouchableOpacity disabled={tooLong || occurrence > 50} onPress={() => first === null ? onSave() : onSave(quote, occurrence)}>
          <Text style={{ color: COLORS.primary }}>{first === null ? "Pin whole paragraph" : "Pin selected quote"}</Text>
        </TouchableOpacity>
        <Text onPress={onClose} style={{ color: COLORS.textSecondary }}>Cancel</Text>
      </View>
    </View>
  </Modal>;
}
