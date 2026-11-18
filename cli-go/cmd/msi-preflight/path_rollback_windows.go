package main

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
)

type pathChange struct {
	Before pathValue
	After  pathValue
}

type pathJournal struct {
	LegacyDirectories []string
	Change            *pathChange
}

func savePathJournal(filename string, journal pathJournal) error {
	temp, err := os.CreateTemp(filepath.Dir(filename), ".wiserec-path-")
	if err != nil {
		return err
	}
	defer os.Remove(temp.Name())
	writeErr := json.NewEncoder(temp).Encode(journal)
	if err := errors.Join(writeErr, temp.Close()); err != nil {
		return err
	}
	return os.Rename(temp.Name(), filename)
}

func readPathJournal(filename string) (pathJournal, error) {
	var journal pathJournal
	data, err := os.ReadFile(filename)
	if errors.Is(err, os.ErrNotExist) {
		return journal, nil
	}
	if err != nil {
		return journal, err
	}
	err = json.Unmarshal(data, &journal)
	return journal, err
}

func restorePath(filename string) error {
	journal, err := readPathJournal(filename)
	if err != nil {
		return err
	}
	change := journal.Change
	if change == nil {
		return removePathJournal(filename)
	}
	current, err := readUserPath()
	if err != nil {
		return err
	}
	// If a separate process changed PATH after the installer, preserve that edit.
	if current == change.After {
		if err := writeUserPath(change.Before); err != nil {
			return err
		}
	}
	return removePathJournal(filename)
}

func removePathJournal(filename string) error {
	err := os.Remove(filename)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	return err
}
