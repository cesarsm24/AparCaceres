import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../shared/constants/app_strings.dart';
import '../../../theme/app_colors.dart';
import '../../../theme/app_spacing.dart';
import '../data/nominatim_client.dart';
import '../domain/place_suggestion.dart';

class LocationPickerScreen extends StatefulWidget {
  const LocationPickerScreen({super.key, NominatimClient? client})
    : _client = client;

  final NominatimClient? _client;

  @override
  State<LocationPickerScreen> createState() => _LocationPickerScreenState();
}

class _LocationPickerScreenState extends State<LocationPickerScreen> {
  static const Duration _debounce = Duration(milliseconds: 400);

  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  late final NominatimClient _client = widget._client ?? NominatimClient();
  late final bool _ownsClient = widget._client == null;

  Timer? _timer;
  String _query = '';
  bool _loading = false;
  Object? _error;
  List<PlaceSuggestion> _results = const <PlaceSuggestion>[];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _focusNode.requestFocus();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _controller.dispose();
    _focusNode.dispose();
    if (_ownsClient) _client.close();
    super.dispose();
  }

  void _onChanged(String value) {
    setState(() => _query = value);
    _timer?.cancel();
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      setState(() {
        _results = const <PlaceSuggestion>[];
        _error = null;
        _loading = false;
      });
      return;
    }
    _timer = Timer(_debounce, () => _search(trimmed));
  }

  Future<void> _search(String query) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await _client.search(query);
      if (!mounted || _query.trim() != query) return;
      setState(() {
        _results = results;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
        _results = const <PlaceSuggestion>[];
      });
    }
  }

  void _clear() {
    _controller.clear();
    _onChanged('');
    _focusNode.requestFocus();
  }

  void _select(PlaceSuggestion suggestion) {
    Navigator.of(context).pop(suggestion);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.pageBackground,
      body: Column(
        children: [
          _PickerHeader(
            controller: _controller,
            focusNode: _focusNode,
            hasText: _query.isNotEmpty,
            onChanged: _onChanged,
            onBack: () => Navigator.of(context).maybePop(),
            onClear: _clear,
          ),
          Expanded(child: _buildBody()),
        ],
      ),
    );
  }

  Widget _buildBody() {
    final trimmed = _query.trim();
    if (trimmed.isEmpty) {
      return const _StatusMessage(AppStrings.locationPickerEmpty);
    }
    if (_loading && _results.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return const _StatusMessage(AppStrings.locationPickerError);
    }
    if (_results.isEmpty) {
      return const _StatusMessage(AppStrings.locationPickerNoResults);
    }
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.horizontalPadding,
        AppSpacing.md,
        AppSpacing.horizontalPadding,
        AppSpacing.lg,
      ),
      itemCount: _results.length,
      separatorBuilder: (_, _) => const SizedBox(height: AppSpacing.sm),
      itemBuilder: (_, i) =>
          _SuggestionTile(suggestion: _results[i], onTap: () => _select(_results[i])),
    );
  }
}

class _PickerHeader extends StatelessWidget {
  const _PickerHeader({
    required this.controller,
    required this.focusNode,
    required this.hasText,
    required this.onChanged,
    required this.onBack,
    required this.onClear,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool hasText;
  final ValueChanged<String> onChanged;
  final VoidCallback onBack;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final topPadding = MediaQuery.of(context).padding.top;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(
        statusBarColor: AppColors.primary,
      ),
      child: Container(
        width: double.infinity,
        color: AppColors.primary,
        padding: EdgeInsets.only(
          top: topPadding,
          left: AppSpacing.sm,
          right: AppSpacing.sm,
          bottom: AppSpacing.sm,
        ),
        child: SizedBox(
          height: 52,
          child: Row(
            children: [
              IconButton(
                onPressed: onBack,
                icon: const Icon(
                  Icons.chevron_left,
                  color: AppColors.textOnPrimary,
                  size: 28,
                ),
              ),
              Expanded(
                child: TextField(
                  controller: controller,
                  focusNode: focusNode,
                  onChanged: onChanged,
                  textInputAction: TextInputAction.search,
                  style: const TextStyle(
                    color: AppColors.textPrimary,
                    fontSize: 15,
                  ),
                  decoration: InputDecoration(
                    hintText: AppStrings.locationPickerHint,
                    hintStyle: const TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 15,
                    ),
                    filled: true,
                    fillColor: AppColors.surface,
                    isDense: true,
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.md,
                      vertical: 12,
                    ),
                    prefixIcon: const Icon(
                      Icons.place_outlined,
                      color: AppColors.textSecondary,
                    ),
                    suffixIcon: hasText
                        ? IconButton(
                            onPressed: onClear,
                            icon: const Icon(
                              Icons.close,
                              color: AppColors.textSecondary,
                              size: 20,
                            ),
                          )
                        : null,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
                      borderSide: BorderSide.none,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SuggestionTile extends StatelessWidget {
  const _SuggestionTile({required this.suggestion, required this.onTap});

  final PlaceSuggestion suggestion;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(
                Icons.place_outlined,
                color: AppColors.primary,
                size: 22,
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      suggestion.shortName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      suggestion.displayName,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 12,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: AppColors.textSecondary),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatusMessage extends StatelessWidget {
  const _StatusMessage(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Center(
        child: Text(
          text,
          textAlign: TextAlign.center,
          style: const TextStyle(color: AppColors.textSecondary, fontSize: 14),
        ),
      ),
    );
  }
}
